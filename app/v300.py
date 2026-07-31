from __future__ import annotations

"""Version 3.0.0: Produktionsfreigabe, Signaturen, Secrets und Marketplace-Automatik."""

import base64
import hashlib
import json
import os
import re
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v250 import app

VERSION = "3.0.0"
base.VERSION = VERSION
app.version = VERSION
STATE = Path(os.getenv("ITPZ_STATE_DIR", "/var/lib/it-projektzentrale"))
MASTER_KEY_FILE = Path(os.getenv("ITPZ_MASTER_KEY_FILE", "/etc/it-projektzentrale.master.key"))
PLUGIN_UPLOADS = STATE / "uploads" / "plugins"
MAX_PACKAGE = int(os.getenv("ITPZ_MARKETPLACE_MAX_PACKAGE", "268435456"))
PLUGIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def init_v300_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS encrypted_secrets (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, value_encrypted BLOB NOT NULL,
          scope TEXT NOT NULL DEFAULT 'global', updated_by INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(updated_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS marketplace_sync_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, catalog_id INTEGER, state TEXT NOT NULL,
          packages_seen INTEGER NOT NULL DEFAULT 0, packages_changed INTEGER NOT NULL DEFAULT 0,
          error TEXT NOT NULL DEFAULT '', started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT,
          FOREIGN KEY(catalog_id) REFERENCES marketplace_catalogs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS revoked_artifacts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, artifact_type TEXT NOT NULL, fingerprint TEXT NOT NULL,
          reason TEXT NOT NULL DEFAULT '', revoked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(artifact_type,fingerprint)
        );
        CREATE TABLE IF NOT EXISTS recovery_points (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, archive_path TEXT NOT NULL,
          sha256 TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'ready', created_by INTEGER,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_marketplace_sync_catalog ON marketplace_sync_runs(catalog_id,id DESC);
        """)


@app.on_event("startup")
def initialize_v300() -> None:
    init_v300_db()
    PLUGIN_UPLOADS.mkdir(parents=True, exist_ok=True)


def _fernet() -> Fernet:
    try:
        key = MASTER_KEY_FILE.read_bytes().strip()
    except OSError as exc:
        raise HTTPException(503, "Master-Key ist nicht verfügbar") from exc
    try:
        return Fernet(key)
    except Exception as exc:
        raise HTTPException(503, "Master-Key ist ungültig") from exc


def _publisher_key(fingerprint: str) -> Ed25519PublicKey:
    with db() as conn:
        row = conn.execute("SELECT public_key,trusted FROM marketplace_publishers WHERE fingerprint=?", (fingerprint,)).fetchone()
        revoked = conn.execute("SELECT 1 FROM revoked_artifacts WHERE artifact_type='publisher' AND fingerprint=?", (fingerprint,)).fetchone()
    if not row or not row["trusted"] or revoked:
        raise HTTPException(403, "Herausgeber ist nicht vertrauenswürdig oder wurde gesperrt")
    try:
        raw = base64.b64decode(row["public_key"], validate=True)
        if hashlib.sha256(raw).hexdigest() != fingerprint:
            raise ValueError("fingerprint mismatch")
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise HTTPException(400, "Ungültiger Ed25519-Schlüssel") from exc


def _verify_signature(public_key: Ed25519PublicKey, payload: bytes, signature: str) -> None:
    try:
        public_key.verify(base64.b64decode(signature, validate=True), payload)
    except Exception as exc:
        raise HTTPException(400, "Signaturprüfung fehlgeschlagen") from exc


def _https_json(url: str, max_bytes: int = 5_000_000) -> dict:
    if not url.startswith("https://"):
        raise HTTPException(400, "Nur HTTPS-Quellen sind zulässig")
    request = urllib.request.Request(url, headers={"User-Agent": f"IT-Projektzentrale/{VERSION}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            length = int(response.headers.get("Content-Length", "0") or 0)
            if length > max_bytes:
                raise HTTPException(413, "Katalog ist zu groß")
            data = response.read(max_bytes + 1)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Katalogabruf fehlgeschlagen: {exc}") from exc
    if len(data) > max_bytes:
        raise HTTPException(413, "Katalog ist zu groß")
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Katalog enthält kein gültiges JSON") from exc


def _sync_catalog(catalog_id: int) -> tuple[int, int]:
    with db() as conn:
        catalog = conn.execute("SELECT c.*,p.fingerprint,p.public_key,p.trusted FROM marketplace_catalogs c JOIN marketplace_publishers p ON p.id=c.publisher_id WHERE c.id=? AND c.enabled=1", (catalog_id,)).fetchone()
        if not catalog:
            raise HTTPException(404, "Aktiver Katalog wurde nicht gefunden")
        run_id = conn.execute("INSERT INTO marketplace_sync_runs(catalog_id,state) VALUES(?, 'running')", (catalog_id,)).lastrowid
    try:
        envelope = _https_json(catalog["catalog_url"])
        payload_b64 = envelope.get("payload", "")
        signature = envelope.get("signature", "")
        payload = base64.b64decode(payload_b64, validate=True)
        key = _publisher_key(catalog["fingerprint"])
        _verify_signature(key, payload, signature)
        document = json.loads(payload)
        packages = document.get("packages", [])
        if not isinstance(packages, list) or len(packages) > 5000:
            raise HTTPException(400, "Ungültige Paketliste")
        changed = 0
        with db() as conn:
            conn.execute("UPDATE marketplace_packages SET available=0 WHERE catalog_id=?", (catalog_id,))
            for item in packages:
                pid = str(item.get("id", "")).lower()
                version = str(item.get("version", ""))[:40]
                digest = str(item.get("sha256", "")).lower()
                url = str(item.get("url", ""))[:1000]
                if not PLUGIN_RE.fullmatch(pid) or not re.fullmatch(r"[a-f0-9]{64}", digest) or not url.startswith("https://"):
                    raise HTTPException(400, f"Ungültiger Paketeintrag: {pid}")
                manifest = item.get("manifest", {})
                signature_item = str(item.get("signature", ""))
                existing = conn.execute("SELECT id,sha256 FROM marketplace_packages WHERE catalog_id=? AND plugin_id=? AND version=?", (catalog_id, pid, version)).fetchone()
                conn.execute("""INSERT INTO marketplace_packages(catalog_id,plugin_id,name,version,description,package_url,sha256,signature,publisher_fingerprint,permissions_json,dependencies_json,manifest_json,available)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)
                  ON CONFLICT(catalog_id,plugin_id,version) DO UPDATE SET name=excluded.name,description=excluded.description,package_url=excluded.package_url,sha256=excluded.sha256,signature=excluded.signature,permissions_json=excluded.permissions_json,dependencies_json=excluded.dependencies_json,manifest_json=excluded.manifest_json,available=1""",
                  (catalog_id,pid,str(item.get("name",pid))[:120],version,str(item.get("description",""))[:1000],url,digest,signature_item,catalog["fingerprint"],json.dumps(manifest.get("permissions",[])),json.dumps(manifest.get("dependencies",[])),json.dumps(manifest)))
                if not existing or existing["sha256"] != digest:
                    changed += 1
            conn.execute("UPDATE marketplace_catalogs SET last_status='ok',last_error='',last_synced_at=CURRENT_TIMESTAMP WHERE id=?", (catalog_id,))
            conn.execute("UPDATE marketplace_sync_runs SET state='succeeded',packages_seen=?,packages_changed=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (len(packages),changed,run_id))
        return len(packages), changed
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE marketplace_catalogs SET last_status='failed',last_error=? WHERE id=?", (str(exc)[:2000],catalog_id))
            conn.execute("UPDATE marketplace_sync_runs SET state='failed',error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:10000],run_id))
        raise


def _download_package(package_id: int) -> Path:
    with db() as conn:
        package = conn.execute("SELECT * FROM marketplace_packages WHERE id=? AND available=1", (package_id,)).fetchone()
        revoked = conn.execute("SELECT 1 FROM revoked_artifacts WHERE artifact_type='package' AND fingerprint=?", (package["sha256"] if package else "",)).fetchone()
    if not package or revoked:
        raise HTTPException(404, "Paket wurde nicht gefunden oder ist gesperrt")
    key = _publisher_key(package["publisher_fingerprint"])
    url = package["package_url"]
    if not url.startswith("https://"):
        raise HTTPException(400, "Nur HTTPS-Pakete sind zulässig")
    filename = f"{package['plugin_id']}_{package['version']}.tar.gz"
    target = PLUGIN_UPLOADS / filename
    request = urllib.request.Request(url, headers={"User-Agent": f"IT-Projektzentrale/{VERSION}"})
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=PLUGIN_UPLOADS, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        total = 0
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_PACKAGE:
                        raise HTTPException(413, "Plugin-Paket ist zu groß")
                    digest.update(chunk)
                    tmp.write(chunk)
            if digest.hexdigest() != package["sha256"]:
                raise HTTPException(400, "SHA256-Prüfung fehlgeschlagen")
            if package["signature"]:
                _verify_signature(key, bytes.fromhex(package["sha256"]), package["signature"])
            os.chmod(tmp_path, 0o640)
            tmp_path.replace(target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    return target


@app.get("/security", response_class=HTMLResponse)
def security_page(request: Request, message: str = "", error: str = ""):
    require_admin(request)
    with db() as conn:
        secrets = [dict(r) for r in conn.execute("SELECT id,name,scope,created_at,updated_at FROM encrypted_secrets ORDER BY name")]
        revoked = [dict(r) for r in conn.execute("SELECT * FROM revoked_artifacts ORDER BY revoked_at DESC")]
        sync_runs = [dict(r) for r in conn.execute("SELECT r.*,c.name catalog_name FROM marketplace_sync_runs r LEFT JOIN marketplace_catalogs c ON c.id=r.catalog_id ORDER BY r.id DESC LIMIT 100")]
        recovery = [dict(r) for r in conn.execute("SELECT * FROM recovery_points ORDER BY id DESC LIMIT 100")]
    return render("security.html", request, title="Sicherheit & Recovery", secrets=secrets, revoked=revoked, sync_runs=sync_runs, recovery=recovery, message=message, error=error)


@app.post("/security/secrets/set")
def secret_set(request: Request, name: str = Form(...), value: str = Form(...), scope: str = Form("global")):
    user = require_admin(request)
    clean_name = re.sub(r"[^A-Za-z0-9_.-]", "", name)[:120]
    if not clean_name or not value:
        raise HTTPException(400, "Name und Wert sind erforderlich")
    encrypted = _fernet().encrypt(value.encode())
    with db() as conn:
        conn.execute("INSERT INTO encrypted_secrets(name,value_encrypted,scope,updated_by) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET value_encrypted=excluded.value_encrypted,scope=excluded.scope,updated_by=excluded.updated_by,updated_at=CURRENT_TIMESTAMP", (clean_name, encrypted, scope[:80], user["id"]))
    audit("security.secret_set", None, clean_name)
    return RedirectResponse("/security?message=Secret+wurde+verschlüsselt+gespeichert", 303)


@app.post("/security/secrets/{secret_id}/delete")
def secret_delete(secret_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        conn.execute("DELETE FROM encrypted_secrets WHERE id=?", (secret_id,))
    audit("security.secret_deleted", secret_id, "")
    return RedirectResponse("/security?message=Secret+wurde+gelöscht", 303)


@app.post("/security/revoke")
def revoke_artifact(request: Request, artifact_type: str = Form(...), fingerprint: str = Form(...), reason: str = Form("")):
    require_admin(request)
    if artifact_type not in {"publisher", "package"} or not re.fullmatch(r"[a-fA-F0-9]{64}", fingerprint):
        raise HTTPException(400, "Ungültiger Sperreintrag")
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO revoked_artifacts(artifact_type,fingerprint,reason,revoked_at) VALUES(?,?,?,CURRENT_TIMESTAMP)", (artifact_type,fingerprint.lower(),reason[:1000]))
    audit("security.artifact_revoked", None, f"{artifact_type}:{fingerprint}")
    return RedirectResponse("/security?message=Artefakt+wurde+gesperrt", 303)


@app.post("/marketplace/catalogs/{catalog_id}/sync")
def marketplace_catalog_sync(catalog_id: int, request: Request):
    require_admin(request)
    try:
        seen, changed = _sync_catalog(catalog_id)
        audit("marketplace.catalog_synced", catalog_id, f"seen={seen},changed={changed}")
        return RedirectResponse(f"/marketplace?message=Katalog+synchronisiert%3A+{seen}+Pakete", 303)
    except Exception as exc:
        return RedirectResponse("/marketplace?error=" + urllib.parse.quote(str(exc)[:700]), 303)


@app.post("/marketplace/packages/{package_id}/download")
def marketplace_package_download(package_id: int, request: Request):
    require_admin(request)
    try:
        path = _download_package(package_id)
        audit("marketplace.package_downloaded", package_id, path.name)
        return RedirectResponse("/marketplace?message=Paket+wurde+geprüft+heruntergeladen", 303)
    except Exception as exc:
        return RedirectResponse("/marketplace?error=" + urllib.parse.quote(str(exc)[:700]), 303)


@app.post("/marketplace/upload")
async def marketplace_upload(request: Request, file: UploadFile):
    require_admin(request)
    name = Path(file.filename or "").name
    if not name.endswith((".tar.gz", ".tgz", ".tar")):
        raise HTTPException(400, "Nicht unterstütztes Plugin-Paket")
    target = PLUGIN_UPLOADS / name
    total = 0
    with tempfile.NamedTemporaryFile(dir=PLUGIN_UPLOADS, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_PACKAGE:
                    raise HTTPException(413, "Plugin-Paket ist zu groß")
                tmp.write(chunk)
            os.chmod(tmp_path, 0o640)
            tmp_path.replace(target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    audit("marketplace.package_uploaded", None, name)
    return RedirectResponse("/marketplace?message=Plugin-Paket+wurde+hochgeladen", 303)


@app.get("/api/v1/security")
def security_api(request: Request):
    require_admin(request)
    with db() as conn:
        return {
            "version": VERSION,
            "secret_count": conn.execute("SELECT COUNT(*) FROM encrypted_secrets").fetchone()[0],
            "revoked": [dict(r) for r in conn.execute("SELECT artifact_type,fingerprint,reason,revoked_at FROM revoked_artifacts ORDER BY id DESC")],
            "sync_runs": [dict(r) for r in conn.execute("SELECT * FROM marketplace_sync_runs ORDER BY id DESC LIMIT 100")],
            "recovery_points": [dict(r) for r in conn.execute("SELECT id,name,sha256,state,created_at FROM recovery_points ORDER BY id DESC LIMIT 100")],
        }
