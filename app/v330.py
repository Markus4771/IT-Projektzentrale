from __future__ import annotations

"""Version 3.3.0: Remote-Projekterkennung, Release-Staging und Installationsübergabe."""

import base64
import fnmatch
import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v300 import _fernet
from app.v320 import _parse_manifest_text, _store_manifest, app

VERSION = "3.3.0"
base.VERSION = VERSION
app.version = VERSION

STATE = Path(os.getenv("ITPZ_STATE_DIR", "/var/lib/it-projektzentrale"))
PACKAGE_DIR = STATE / "uploads" / "packages"
MAX_MANIFEST = 256 * 1024
MAX_PACKAGE = int(os.getenv("ITPZ_MAX_UPLOAD_BYTES", "268435456"))
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
ALLOWED_PROVIDERS = {"github", "gitea"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise HTTPException(502, "HTTP-Weiterleitungen sind für Remote-Quellen deaktiviert")


def init_remote_discovery_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS project_remote_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            provider TEXT NOT NULL,
            base_url TEXT NOT NULL,
            repository TEXT NOT NULL,
            branch TEXT NOT NULL DEFAULT 'main',
            manifest_path TEXT NOT NULL DEFAULT 'projekt.yaml',
            secret_name TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_status TEXT NOT NULL DEFAULT 'never',
            last_error TEXT NOT NULL DEFAULT '',
            last_synced_at TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider,base_url,repository,branch,manifest_path),
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS project_remote_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            state TEXT NOT NULL,
            manifest_id INTEGER,
            release_version TEXT NOT NULL DEFAULT '',
            assets_seen INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            FOREIGN KEY(source_id) REFERENCES project_remote_sources(id) ON DELETE CASCADE,
            FOREIGN KEY(manifest_id) REFERENCES project_manifests(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS project_release_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            manifest_id INTEGER,
            release_version TEXT NOT NULL,
            asset_name TEXT NOT NULL,
            asset_url TEXT NOT NULL,
            expected_sha256 TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'detected',
            local_path TEXT NOT NULL DEFAULT '',
            actual_sha256 TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            downloaded_at TEXT,
            UNIQUE(source_id,release_version,asset_name),
            FOREIGN KEY(source_id) REFERENCES project_remote_sources(id) ON DELETE CASCADE,
            FOREIGN KEY(manifest_id) REFERENCES project_manifests(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_remote_sources_enabled ON project_remote_sources(enabled,id);
        CREATE INDEX IF NOT EXISTS idx_remote_runs_source ON project_remote_sync_runs(source_id,id DESC);
        CREATE INDEX IF NOT EXISTS idx_release_assets_source ON project_release_assets(source_id,id DESC);
        """)


@app.on_event("startup")
def initialize_v330() -> None:
    init_remote_discovery_db()
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)


def _safe_https_base(value: str, provider: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        value = "https://api.github.com" if provider == "github" else ""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Remote-Quellen benötigen eine HTTPS-Basisadresse ohne Zugangsdaten")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise HTTPException(400, "Hostname der Remote-Quelle kann nicht aufgelöst werden") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise HTTPException(400, "Private oder reservierte Remote-Ziele sind nicht zulässig")
    return value


def _secret(name: str) -> str:
    if not name:
        return ""
    with db() as conn:
        row = conn.execute("SELECT value_encrypted FROM encrypted_secrets WHERE name=?", (name,)).fetchone()
    if not row:
        raise HTTPException(409, f"Secret {name} wurde nicht gefunden")
    try:
        return _fernet().decrypt(row["value_encrypted"]).decode()
    except Exception as exc:
        raise HTTPException(503, "Remote-Secret kann nicht entschlüsselt werden") from exc


def _headers(source: dict[str, Any]) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": f"IT-Projektzentrale/{VERSION}"}
    token = _secret(source.get("secret_name", ""))
    if token:
        headers["Authorization"] = f"Bearer {token}" if source["provider"] == "github" else f"token {token}"
    return headers


def _request_bytes(url: str, headers: dict[str, str], limit: int, timeout: int = 30) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(400, "Nur HTTPS-Abrufe sind zulässig")
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(request, timeout=timeout) as response:
            length = int(response.headers.get("Content-Length", "0") or 0)
            if length > limit:
                raise HTTPException(413, "Remote-Inhalt ist zu groß")
            data = response.read(limit + 1)
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        raise HTTPException(502, f"Remote-Quelle antwortet mit HTTP {exc.code}") from exc
    except Exception as exc:
        raise HTTPException(502, f"Remote-Abruf fehlgeschlagen: {exc}") from exc
    if len(data) > limit:
        raise HTTPException(413, "Remote-Inhalt ist zu groß")
    return data


def _request_json(url: str, headers: dict[str, str], limit: int = 5_000_000) -> dict[str, Any]:
    try:
        value = json.loads(_request_bytes(url, headers, limit))
    except json.JSONDecodeError as exc:
        raise HTTPException(502, "Remote-Quelle liefert kein gültiges JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(502, "Remote-Antwort hat ein unerwartetes Format")
    return value


def _api_urls(source: dict[str, Any]) -> tuple[str, str]:
    base_url = source["base_url"].rstrip("/")
    repo = urllib.parse.quote(source["repository"], safe="/")
    path = urllib.parse.quote(source["manifest_path"], safe="/")
    branch = urllib.parse.quote(source["branch"], safe="")
    if source["provider"] == "github":
        return (
            f"{base_url}/repos/{repo}/contents/{path}?ref={branch}",
            f"{base_url}/repos/{repo}/releases/latest",
        )
    return (
        f"{base_url}/api/v1/repos/{repo}/contents/{path}?ref={branch}",
        f"{base_url}/api/v1/repos/{repo}/releases/latest",
    )


def _decode_manifest(document: dict[str, Any]) -> str:
    content = document.get("content", "")
    encoding = document.get("encoding", "base64")
    if encoding != "base64" or not isinstance(content, str):
        raise HTTPException(502, "Remote-Manifest wird nicht als Base64 geliefert")
    try:
        raw = base64.b64decode(content, validate=False)
        return raw.decode("utf-8")
    except Exception as exc:
        raise HTTPException(502, "Remote-Manifest kann nicht dekodiert werden") from exc


def _release_assets(document: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    tag = str(document.get("tag_name") or document.get("name") or "")[:80]
    version = tag[1:] if tag.startswith("v") else tag
    assets = document.get("assets") or []
    if not isinstance(assets, list) or len(assets) > 500:
        raise HTTPException(502, "Release enthält eine ungültige Asset-Liste")
    normalized = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")[:255]
        url = str(item.get("browser_download_url") or item.get("url") or "")[:2000]
        size = int(item.get("size") or 0)
        if name and url.startswith("https://"):
            normalized.append({"name": name, "url": url, "size": max(0, size)})
    return version, normalized


def _sync_source(source_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM project_remote_sources WHERE id=? AND enabled=1", (source_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Aktive Remote-Quelle wurde nicht gefunden")
        source = dict(row)
        run_id = conn.execute("INSERT INTO project_remote_sync_runs(source_id,state) VALUES(?,'running')", (source_id,)).lastrowid
    try:
        manifest_url, release_url = _api_urls(source)
        headers = _headers(source)
        manifest_doc = _request_json(manifest_url, headers, MAX_MANIFEST * 2)
        manifest, digest = _parse_manifest_text(_decode_manifest(manifest_doc))
        if manifest["source"]["provider"] != source["provider"] or manifest["source"]["repository"] != source["repository"]:
            raise HTTPException(409, "Manifestquelle stimmt nicht mit der registrierten Remote-Quelle überein")
        manifest_id = _store_manifest(manifest, digest, f"remote:{source['provider']}:{source['repository']}")

        release_version = ""
        assets: list[dict[str, Any]] = []
        try:
            release_version, assets = _release_assets(_request_json(release_url, headers))
        except HTTPException as exc:
            if "HTTP 404" not in str(exc.detail):
                raise

        pattern = str(manifest.get("package", {}).get("asset") or "*.deb")[:255]
        expected = str(manifest.get("package", {}).get("sha256") or "").lower()
        if expected and not SHA256_RE.fullmatch(expected):
            raise HTTPException(400, "package.sha256 im Manifest ist ungültig")
        matching = [asset for asset in assets if fnmatch.fnmatchcase(asset["name"], pattern)]
        if len(matching) > 1:
            raise HTTPException(409, "Mehrere Release-Assets passen zum Manifestmuster")
        with db() as conn:
            for asset in matching:
                conn.execute("""INSERT INTO project_release_assets(source_id,manifest_id,release_version,asset_name,asset_url,expected_sha256,size_bytes)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id,release_version,asset_name) DO UPDATE SET
                    manifest_id=excluded.manifest_id,asset_url=excluded.asset_url,expected_sha256=excluded.expected_sha256,
                    size_bytes=excluded.size_bytes,state=CASE WHEN project_release_assets.state='downloaded' THEN state ELSE 'detected' END,error=''""",
                    (source_id, manifest_id, release_version, asset["name"], asset["url"], expected, asset["size"]))
            conn.execute("UPDATE project_remote_sources SET last_status='ok',last_error='',last_synced_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (source_id,))
            conn.execute("UPDATE project_remote_sync_runs SET state='succeeded',manifest_id=?,release_version=?,assets_seen=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (manifest_id, release_version, len(assets), run_id))
        audit("project_remote.synced", source_id, f"{manifest['id']}:{manifest['version']}")
        return {"manifest": manifest, "release_version": release_version, "matching_assets": len(matching)}
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE project_remote_sources SET last_status='failed',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:2000], source_id))
            conn.execute("UPDATE project_remote_sync_runs SET state='failed',error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:10000], run_id))
        raise


def _download_asset(asset_id: int) -> Path:
    with db() as conn:
        row = conn.execute("SELECT a.*,s.provider,s.secret_name FROM project_release_assets a JOIN project_remote_sources s ON s.id=a.source_id WHERE a.id=?", (asset_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Release-Asset wurde nicht gefunden")
    asset = dict(row)
    if not asset["expected_sha256"]:
        raise HTTPException(409, "Automatischer Download benötigt package.sha256 im Manifest")
    if asset["size_bytes"] and asset["size_bytes"] > MAX_PACKAGE:
        raise HTTPException(413, "Release-Paket ist zu groß")
    safe_name = Path(asset["asset_name"]).name
    if safe_name != asset["asset_name"] or not safe_name.endswith(".deb"):
        raise HTTPException(400, "Nur sichere Debian-Paketdateien werden unterstützt")
    target = PACKAGE_DIR / safe_name
    headers = {"User-Agent": f"IT-Projektzentrale/{VERSION}", "Accept": "application/octet-stream"}
    token = _secret(asset["secret_name"])
    if token:
        headers["Authorization"] = f"Bearer {token}" if asset["provider"] == "github" else f"token {token}"
    data = _request_bytes(asset["asset_url"], headers, MAX_PACKAGE, timeout=90)
    digest = hashlib.sha256(data).hexdigest()
    if digest != asset["expected_sha256"]:
        raise HTTPException(400, "SHA256-Prüfung des Release-Pakets ist fehlgeschlagen")
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=PACKAGE_DIR, delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fchmod(tmp.fileno(), 0o640)
        tmp_path = Path(tmp.name)
    tmp_path.replace(target)
    with db() as conn:
        conn.execute("UPDATE project_release_assets SET state='downloaded',local_path=?,actual_sha256=?,error='',downloaded_at=CURRENT_TIMESTAMP WHERE id=?", (str(target), digest, asset_id))
    audit("project_remote.asset_downloaded", asset_id, safe_name)
    return target


def _summary() -> dict[str, Any]:
    with db() as conn:
        sources = [dict(r) for r in conn.execute("SELECT * FROM project_remote_sources ORDER BY name")]
        runs = [dict(r) for r in conn.execute("SELECT r.*,s.name source_name FROM project_remote_sync_runs r JOIN project_remote_sources s ON s.id=r.source_id ORDER BY r.id DESC LIMIT 50")]
        assets = [dict(r) for r in conn.execute("SELECT a.*,s.name source_name,m.project_key FROM project_release_assets a JOIN project_remote_sources s ON s.id=a.source_id LEFT JOIN project_manifests m ON m.id=a.manifest_id ORDER BY a.id DESC LIMIT 100")]
        secrets = [r["name"] for r in conn.execute("SELECT name FROM encrypted_secrets ORDER BY name")]
    return {"sources": sources, "runs": runs, "assets": assets, "secret_names": secrets}


@app.get("/project-framework/remotes", response_class=HTMLResponse)
def remote_sources_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    return render("project_remote_sources.html", request, title="Remote-Projektquellen", message=message, error=error, **_summary())


@app.post("/project-framework/remotes")
def remote_source_add(request: Request, name: str = Form(...), provider: str = Form(...), base_url: str = Form(""), repository: str = Form(...), branch: str = Form("main"), manifest_path: str = Form("projekt.yaml"), secret_name: str = Form("")):
    user = require_admin(request)
    provider = provider.strip().lower()
    repository = repository.strip()
    if provider not in ALLOWED_PROVIDERS or not REPOSITORY_RE.fullmatch(repository):
        raise HTTPException(400, "Ungültiger Anbieter oder Repositoryname")
    clean_branch = branch.strip()[:120] or "main"
    clean_path = manifest_path.strip().strip("/")[:240] or "projekt.yaml"
    if ".." in Path(clean_path).parts or not clean_path.endswith(('.yaml', '.yml')):
        raise HTTPException(400, "Ungültiger Manifestpfad")
    clean_url = _safe_https_base(base_url, provider)
    with db() as conn:
        conn.execute("INSERT INTO project_remote_sources(name,provider,base_url,repository,branch,manifest_path,secret_name,created_by) VALUES(?,?,?,?,?,?,?,?)", (name.strip()[:120], provider, clean_url, repository, clean_branch, clean_path, secret_name.strip()[:120], user["id"]))
    audit("project_remote.source_added", None, f"{provider}:{repository}")
    return RedirectResponse("/project-framework/remotes?message=Remote-Quelle+wurde+angelegt", 303)


@app.post("/project-framework/remotes/{source_id}/sync")
def remote_source_sync(source_id: int, request: Request):
    require_admin(request)
    try:
        result = _sync_source(source_id)
        message = urllib.parse.quote(f"Synchronisiert: {result['manifest']['name']} {result['manifest']['version']}")
        return RedirectResponse(f"/project-framework/remotes?message={message}", 303)
    except HTTPException as exc:
        return RedirectResponse("/project-framework/remotes?error=" + urllib.parse.quote(str(exc.detail)), 303)


@app.post("/project-framework/assets/{asset_id}/download")
def remote_asset_download(asset_id: int, request: Request):
    require_admin(request)
    try:
        path = _download_asset(asset_id)
        return RedirectResponse("/project-framework/remotes?message=" + urllib.parse.quote(f"Paket geprüft: {path.name}"), 303)
    except HTTPException as exc:
        with db() as conn:
            conn.execute("UPDATE project_release_assets SET state='failed',error=? WHERE id=?", (str(exc.detail)[:2000], asset_id))
        return RedirectResponse("/project-framework/remotes?error=" + urllib.parse.quote(str(exc.detail)), 303)


@app.post("/project-framework/assets/{asset_id}/install")
def remote_asset_install(asset_id: int, request: Request):
    user = require_admin(request)
    with db() as conn:
        asset = conn.execute("SELECT a.*,m.project_key,m.manifest_json FROM project_release_assets a JOIN project_manifests m ON m.id=a.manifest_id WHERE a.id=? AND a.state='downloaded'", (asset_id,)).fetchone()
        if not asset:
            raise HTTPException(409, "Das Paket wurde noch nicht erfolgreich heruntergeladen")
        project = conn.execute("SELECT id FROM projects WHERE slug=? AND deleted_at IS NULL", (asset["project_key"],)).fetchone()
        if not project:
            raise HTTPException(409, "Manifest muss zuerst in den Projektkatalog übernommen werden")
        duplicate = conn.execute("SELECT 1 FROM installation_jobs WHERE project_id=? AND state IN ('queued','running')", (project["id"],)).fetchone()
        if duplicate:
            raise HTTPException(409, "Für dieses Projekt läuft bereits ein Installationsauftrag")
        cursor = conn.execute("""INSERT INTO installation_jobs(project_id,job_type,package_file,source,created_by,phase,target_version)
            VALUES(?,'install',?,?,?,'queued',?)""", (project["id"], asset["local_path"], f"remote-asset:{asset_id}", user["id"], asset["release_version"]))
    audit("project_remote.install_queued", project["id"], f"asset:{asset_id}")
    return RedirectResponse(f"/installation/jobs/{cursor.lastrowid}", 303)


@app.get("/api/v1/project-remotes")
def remote_sources_api(request: Request):
    require_user(request)
    summary = _summary()
    return {"version": VERSION, "sources": summary["sources"], "runs": summary["runs"], "assets": summary["assets"]}
