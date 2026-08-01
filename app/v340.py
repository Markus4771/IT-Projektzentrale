from __future__ import annotations

"""Version 3.4.0: Kontenweite Repository-Erkennung, App-Store-Katalog und Projekt-SDK."""

import json
import re
import urllib.parse
from typing import Any

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v320 import _parse_manifest_text, _store_manifest
from app.v330 import (
    ALLOWED_PROVIDERS,
    MAX_MANIFEST,
    _decode_manifest,
    _request_json,
    _safe_https_base,
    _secret,
    app,
)

VERSION = "3.4.0"
base.VERSION = VERSION
app.version = VERSION

OWNER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
MAX_PAGES = 20


def init_repository_catalog_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS repository_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            provider TEXT NOT NULL,
            base_url TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT '',
            secret_name TEXT NOT NULL DEFAULT '',
            include_forks INTEGER NOT NULL DEFAULT 0,
            include_archived INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_status TEXT NOT NULL DEFAULT 'never',
            last_error TEXT NOT NULL DEFAULT '',
            last_scanned_at TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider,base_url,owner),
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS discovered_repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            repository TEXT NOT NULL,
            default_branch TEXT NOT NULL DEFAULT 'main',
            description TEXT NOT NULL DEFAULT '',
            private INTEGER NOT NULL DEFAULT 0,
            fork INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            web_url TEXT NOT NULL DEFAULT '',
            manifest_state TEXT NOT NULL DEFAULT 'unknown',
            manifest_id INTEGER,
            manifest_error TEXT NOT NULL DEFAULT '',
            selected INTEGER NOT NULL DEFAULT 1,
            discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id,repository),
            FOREIGN KEY(account_id) REFERENCES repository_accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(manifest_id) REFERENCES project_manifests(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS repository_discovery_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            state TEXT NOT NULL,
            repositories_seen INTEGER NOT NULL DEFAULT 0,
            manifests_found INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            details TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            FOREIGN KEY(account_id) REFERENCES repository_accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_repo_accounts_enabled ON repository_accounts(enabled,id);
        CREATE INDEX IF NOT EXISTS idx_discovered_repo_account ON discovered_repositories(account_id,repository);
        CREATE INDEX IF NOT EXISTS idx_discovery_runs_account ON repository_discovery_runs(account_id,id DESC);
        """)


@app.on_event("startup")
def initialize_v340() -> None:
    init_repository_catalog_db()


def _account_headers(account: dict[str, Any]) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": f"IT-Projektzentrale/{VERSION}"}
    token = _secret(account.get("secret_name", ""))
    if token:
        headers["Authorization"] = f"Bearer {token}" if account["provider"] == "github" else f"token {token}"
    return headers


def _repository_pages(account: dict[str, Any]):
    base_url = account["base_url"].rstrip("/")
    owner = account["owner"]
    headers = _account_headers(account)
    for page in range(1, MAX_PAGES + 1):
        if account["provider"] == "github":
            if owner:
                url = f"{base_url}/orgs/{urllib.parse.quote(owner, safe='')}/repos?per_page=100&page={page}&sort=updated"
            else:
                url = f"{base_url}/user/repos?per_page=100&page={page}&sort=updated&affiliation=owner,organization_member"
        else:
            api = f"{base_url}/api/v1"
            if owner:
                url = f"{api}/orgs/{urllib.parse.quote(owner, safe='')}/repos?limit=50&page={page}"
            else:
                url = f"{api}/user/repos?limit=50&page={page}"
        document = _request_json_list(url, headers)
        if not document:
            break
        yield from document
        if len(document) < (100 if account["provider"] == "github" else 50):
            break


def _request_json_list(url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    from app.v330 import _request_bytes

    try:
        value = json.loads(_request_bytes(url, headers, 10_000_000, timeout=45))
    except json.JSONDecodeError as exc:
        raise HTTPException(502, "Repository-API liefert kein gültiges JSON") from exc
    if not isinstance(value, list) or len(value) > 1000:
        raise HTTPException(502, "Repository-API liefert ein unerwartetes Format")
    return [item for item in value if isinstance(item, dict)]


def _normalize_repository(account: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    full_name = str(item.get("full_name") or "")
    if not full_name and item.get("owner") and item.get("name"):
        owner = item["owner"].get("login") or item["owner"].get("username") or item["owner"].get("name")
        full_name = f"{owner}/{item['name']}" if owner else ""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
        return None
    fork = bool(item.get("fork"))
    archived = bool(item.get("archived"))
    if fork and not account["include_forks"]:
        return None
    if archived and not account["include_archived"]:
        return None
    return {
        "repository": full_name,
        "default_branch": str(item.get("default_branch") or "main")[:120],
        "description": str(item.get("description") or "")[:1000],
        "private": int(bool(item.get("private"))),
        "fork": int(fork),
        "archived": int(archived),
        "web_url": str(item.get("html_url") or item.get("website") or "")[:2000],
    }


def _manifest_url(account: dict[str, Any], repository: str, branch: str) -> str:
    base_url = account["base_url"].rstrip("/")
    repo = urllib.parse.quote(repository, safe="/")
    ref = urllib.parse.quote(branch, safe="")
    if account["provider"] == "github":
        return f"{base_url}/repos/{repo}/contents/projekt.yaml?ref={ref}"
    return f"{base_url}/api/v1/repos/{repo}/contents/projekt.yaml?ref={ref}"


def _discover_account(account_id: int) -> dict[str, int]:
    with db() as conn:
        row = conn.execute("SELECT * FROM repository_accounts WHERE id=? AND enabled=1", (account_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Aktives Repository-Konto wurde nicht gefunden")
        account = dict(row)
        run_id = conn.execute("INSERT INTO repository_discovery_runs(account_id,state) VALUES(?,'running')", (account_id,)).lastrowid
    seen = found = errors = 0
    error_details: list[str] = []
    headers = _account_headers(account)
    try:
        for item in _repository_pages(account):
            repo = _normalize_repository(account, item)
            if repo is None:
                continue
            seen += 1
            manifest_state = "missing"
            manifest_id = None
            manifest_error = ""
            try:
                document = _request_json(_manifest_url(account, repo["repository"], repo["default_branch"]), headers, MAX_MANIFEST * 2)
                manifest, digest = _parse_manifest_text(_decode_manifest(document))
                source = manifest.get("source") or {}
                if source.get("provider") not in {"", account["provider"]} or source.get("repository") not in {"", repo["repository"]}:
                    raise HTTPException(409, "projekt.yaml verweist auf ein anderes Repository")
                manifest_id = _store_manifest(manifest, digest, f"account:{account_id}:{repo['repository']}")
                manifest_state = "valid"
                found += 1
            except HTTPException as exc:
                detail = str(exc.detail)
                if "HTTP 404" not in detail:
                    manifest_state = "invalid"
                    manifest_error = detail[:1000]
                    errors += 1
                    error_details.append(f"{repo['repository']}: {detail}")
            with db() as conn:
                conn.execute("""INSERT INTO discovered_repositories(
                    account_id,repository,default_branch,description,private,fork,archived,web_url,
                    manifest_state,manifest_id,manifest_error)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(account_id,repository) DO UPDATE SET
                    default_branch=excluded.default_branch,description=excluded.description,
                    private=excluded.private,fork=excluded.fork,archived=excluded.archived,
                    web_url=excluded.web_url,manifest_state=excluded.manifest_state,
                    manifest_id=excluded.manifest_id,manifest_error=excluded.manifest_error,
                    updated_at=CURRENT_TIMESTAMP""", (
                    account_id, repo["repository"], repo["default_branch"], repo["description"],
                    repo["private"], repo["fork"], repo["archived"], repo["web_url"],
                    manifest_state, manifest_id, manifest_error,
                ))
        with db() as conn:
            conn.execute("UPDATE repository_accounts SET last_status='ok',last_error='',last_scanned_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (account_id,))
            conn.execute("UPDATE repository_discovery_runs SET state='succeeded',repositories_seen=?,manifests_found=?,errors=?,details=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (seen, found, errors, "\n".join(error_details)[:10000], run_id))
        audit("repository_account.discovered", account_id, f"repositories={seen},manifests={found},errors={errors}")
        return {"repositories": seen, "manifests": found, "errors": errors}
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE repository_accounts SET last_status='failed',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:2000], account_id))
            conn.execute("UPDATE repository_discovery_runs SET state='failed',repositories_seen=?,manifests_found=?,errors=?,details=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (seen, found, errors + 1, str(exc)[:10000], run_id))
        raise


def _catalog_summary() -> dict[str, Any]:
    with db() as conn:
        accounts = [dict(r) for r in conn.execute("SELECT * FROM repository_accounts ORDER BY name")]
        repositories = [dict(r) for r in conn.execute("""SELECT d.*,a.name account_name,a.provider,m.project_key,m.version manifest_version,m.name manifest_name
            FROM discovered_repositories d JOIN repository_accounts a ON a.id=d.account_id
            LEFT JOIN project_manifests m ON m.id=d.manifest_id
            ORDER BY d.manifest_state='valid' DESC,a.name,d.repository LIMIT 1000""")]
        runs = [dict(r) for r in conn.execute("""SELECT r.*,a.name account_name FROM repository_discovery_runs r
            JOIN repository_accounts a ON a.id=r.account_id ORDER BY r.id DESC LIMIT 50""")]
        secrets = [r["name"] for r in conn.execute("SELECT name FROM encrypted_secrets ORDER BY name")]
    return {"accounts": accounts, "repositories": repositories, "runs": runs, "secret_names": secrets}


@app.get("/repository-catalog", response_class=HTMLResponse)
def repository_catalog_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    return render("repository_catalog.html", request, title="Repository-Katalog", message=message, error=error, **_catalog_summary())


@app.post("/repository-catalog/accounts")
def repository_account_add(request: Request, name: str = Form(...), provider: str = Form(...), base_url: str = Form(""), owner: str = Form(""), secret_name: str = Form(""), include_forks: bool = Form(False), include_archived: bool = Form(False)):
    user = require_admin(request)
    provider = provider.strip().lower()
    owner = owner.strip()
    if provider not in ALLOWED_PROVIDERS or (owner and not OWNER_RE.fullmatch(owner)):
        raise HTTPException(400, "Ungültiger Anbieter oder Eigentümer")
    clean_url = _safe_https_base(base_url, provider)
    with db() as conn:
        conn.execute("""INSERT INTO repository_accounts(name,provider,base_url,owner,secret_name,include_forks,include_archived,created_by)
            VALUES(?,?,?,?,?,?,?,?)""", (name.strip()[:120], provider, clean_url, owner, secret_name.strip()[:120], int(include_forks), int(include_archived), user["id"]))
    audit("repository_account.added", None, f"{provider}:{owner or 'token-user'}")
    return RedirectResponse("/repository-catalog?message=Repository-Konto+wurde+angelegt", 303)


@app.post("/repository-catalog/accounts/{account_id}/discover")
def repository_account_discover(account_id: int, request: Request):
    require_admin(request)
    try:
        result = _discover_account(account_id)
        text = urllib.parse.quote(f"Erkennung abgeschlossen: {result['repositories']} Repositories, {result['manifests']} Manifeste")
        return RedirectResponse(f"/repository-catalog?message={text}", 303)
    except HTTPException as exc:
        return RedirectResponse("/repository-catalog?error=" + urllib.parse.quote(str(exc.detail)), 303)


@app.post("/repository-catalog/repositories/{repository_id}/apply")
def repository_apply(repository_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        row = conn.execute("""SELECT d.*,m.manifest_json FROM discovered_repositories d
            JOIN project_manifests m ON m.id=d.manifest_id WHERE d.id=? AND d.manifest_state='valid'""", (repository_id,)).fetchone()
        if not row:
            raise HTTPException(409, "Repository besitzt kein gültiges Projektmanifest")
    manifest = json.loads(row["manifest_json"])
    from app.v320 import _apply_manifest
    _apply_manifest(manifest)
    audit("repository_catalog.applied", repository_id, row["repository"])
    return RedirectResponse("/repository-catalog?message=Projekt+wurde+in+den+App-Store+übernommen", 303)


SDK_TEMPLATE = """schema: itpz/v1
id: mein-projekt
name: Mein Projekt
version: 1.0.0
type: deb
channel: stable
category: Allgemein
description: Kurze Beschreibung des Projekts.
homepage: https://example.org
package:
  name: mein-projekt
  asset: mein-projekt_*_all.deb
  sha256: HIER_SHA256_EINTRAGEN
source:
  provider: github
  repository: Eigentümer/Repository
install:
  service: mein-projekt.service
health:
  type: http
  url: http://127.0.0.1:8080/health
permissions:
  - network
"""


@app.get("/project-sdk", response_class=HTMLResponse)
def project_sdk_page(request: Request):
    require_user(request)
    return render("project_sdk.html", request, title="Projekt-SDK", sdk_template=SDK_TEMPLATE)


@app.get("/project-sdk/projekt.yaml", response_class=PlainTextResponse)
def project_sdk_manifest(request: Request):
    require_user(request)
    return PlainTextResponse(SDK_TEMPLATE, media_type="application/yaml", headers={"Content-Disposition": 'attachment; filename="projekt.yaml"'})


@app.post("/project-sdk/validate")
def project_sdk_validate(request: Request, manifest_text: str = Form(...)):
    require_user(request)
    try:
        manifest, digest = _parse_manifest_text(manifest_text)
        message = urllib.parse.quote(f"Gültig: {manifest['name']} {manifest['version']} · SHA256 {digest[:12]}…")
        return RedirectResponse(f"/project-sdk?message={message}", 303)
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return RedirectResponse("/project-sdk?error=" + urllib.parse.quote(str(detail)), 303)


@app.get("/api/v1/repository-catalog")
def repository_catalog_api(request: Request):
    require_user(request)
    summary = _catalog_summary()
    return {"version": VERSION, "accounts": summary["accounts"], "repositories": summary["repositories"], "runs": summary["runs"]}
