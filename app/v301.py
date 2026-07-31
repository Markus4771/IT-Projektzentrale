from __future__ import annotations

"""Version 3.0.1: Stabilitäts- und Sicherheitskorrekturen für 3.0.0."""

import base64
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

from fastapi import HTTPException

import app.main as base
import app.v300 as v300
from app.main import db

app = v300.app
VERSION = "3.0.1"
base.VERSION = VERSION
v300.VERSION = VERSION
app.version = VERSION
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]{0,39}$")
ALLOWED_PERMISSIONS = {"network", "filesystem-read", "filesystem-write", "database-read", "database-write", "notifications", "server-status"}
MAX_REDIRECTS = 3


def _validated_https_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Nur sichere HTTPS-Adressen ohne eingebettete Zugangsdaten sind zulässig")
    try:
        addresses = {item[4][0].split("%", 1)[0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise HTTPException(502, "Hostname konnte nicht aufgelöst werden") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise HTTPException(400, "Private, lokale oder reservierte Zieladressen sind nicht zulässig")
    return urllib.parse.urlunsplit(parsed)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Weiterleitungen sind für Marketplace-Downloads deaktiviert", headers, fp)


def _open_https(url: str, timeout: int):
    safe_url = _validated_https_url(url)
    request = urllib.request.Request(safe_url, headers={"User-Agent": f"IT-Projektzentrale/{VERSION}", "Accept": "application/json, application/octet-stream"})
    opener = urllib.request.build_opener(_NoRedirect())
    return opener.open(request, timeout=timeout)


def _https_json(url: str, max_bytes: int = 5_000_000) -> dict:
    try:
        with _open_https(url, 20) as response:
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
        document = json.loads(data)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Katalog enthält kein gültiges JSON") from exc
    if not isinstance(document, dict):
        raise HTTPException(400, "Katalog muss ein JSON-Objekt sein")
    return document


def _validated_manifest(item: dict, publisher_fingerprint: str) -> tuple[str, str, str, str, dict, list[str], list[str], str]:
    if not isinstance(item, dict):
        raise HTTPException(400, "Paketlisten-Eintrag ist ungültig")
    pid = str(item.get("id", "")).lower()
    version = str(item.get("version", ""))
    digest = str(item.get("sha256", "")).lower()
    url = str(item.get("url", ""))[:1000]
    manifest = item.get("manifest", {})
    if not isinstance(manifest, dict):
        raise HTTPException(400, f"Ungültiges Plugin-Manifest: {pid}")
    permissions = manifest.get("permissions", [])
    dependencies = manifest.get("dependencies", [])
    if not v300.PLUGIN_RE.fullmatch(pid) or not VERSION_RE.fullmatch(version) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise HTTPException(400, f"Ungültiger Paketeintrag: {pid}")
    _validated_https_url(url)
    if manifest.get("id", pid) != pid or manifest.get("version", version) != version or manifest.get("publisher", publisher_fingerprint) != publisher_fingerprint:
        raise HTTPException(400, f"Manifest und Katalogeintrag stimmen nicht überein: {pid}")
    if not isinstance(permissions, list) or any(not isinstance(value, str) or value not in ALLOWED_PERMISSIONS for value in permissions):
        raise HTTPException(400, f"Ungültige Plugin-Berechtigung: {pid}")
    if not isinstance(dependencies, list) or any(not isinstance(value, str) or not v300.PLUGIN_RE.fullmatch(value) for value in dependencies):
        raise HTTPException(400, f"Ungültige Plugin-Abhängigkeit: {pid}")
    signature = str(item.get("signature", ""))
    if not signature:
        raise HTTPException(400, f"Paketsignatur fehlt: {pid}")
    return pid, version, digest, url, manifest, sorted(set(permissions)), sorted(set(dependencies)), signature


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
        if not isinstance(payload_b64, str) or not isinstance(signature, str):
            raise HTTPException(400, "Ungültiger Katalog-Umschlag")
        payload = base64.b64decode(payload_b64, validate=True)
        if len(payload) > 5_000_000:
            raise HTTPException(413, "Signierter Kataloginhalt ist zu groß")
        key = v300._publisher_key(catalog["fingerprint"])
        v300._verify_signature(key, payload, signature)
        document = json.loads(payload)
        packages = document.get("packages", []) if isinstance(document, dict) else None
        if not isinstance(packages, list) or len(packages) > 5000:
            raise HTTPException(400, "Ungültige Paketliste")
        validated = [_validated_manifest(item, catalog["fingerprint"]) for item in packages]
        changed = 0
        with db() as conn:
            conn.execute("UPDATE marketplace_packages SET available=0 WHERE catalog_id=?", (catalog_id,))
            for pid, version, digest, url, manifest, permissions, dependencies, signature_item in validated:
                existing = conn.execute("SELECT id,sha256 FROM marketplace_packages WHERE catalog_id=? AND plugin_id=? AND version=?", (catalog_id, pid, version)).fetchone()
                conn.execute("""INSERT INTO marketplace_packages(catalog_id,plugin_id,name,version,description,package_url,sha256,signature,publisher_fingerprint,permissions_json,dependencies_json,manifest_json,available)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)
                  ON CONFLICT(catalog_id,plugin_id,version) DO UPDATE SET name=excluded.name,description=excluded.description,package_url=excluded.package_url,sha256=excluded.sha256,signature=excluded.signature,permissions_json=excluded.permissions_json,dependencies_json=excluded.dependencies_json,manifest_json=excluded.manifest_json,available=1""",
                  (catalog_id,pid,str(manifest.get("name",pid))[:120],version,str(manifest.get("description",""))[:1000],url,digest,signature_item,catalog["fingerprint"],json.dumps(permissions),json.dumps(dependencies),json.dumps(manifest)))
                if not existing or existing["sha256"] != digest:
                    changed += 1
            conn.execute("UPDATE marketplace_catalogs SET last_status='ok',last_error='',last_synced_at=CURRENT_TIMESTAMP WHERE id=?", (catalog_id,))
            conn.execute("UPDATE marketplace_sync_runs SET state='succeeded',packages_seen=?,packages_changed=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (len(validated),changed,run_id))
        return len(validated), changed
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
    if not VERSION_RE.fullmatch(package["version"]):
        raise HTTPException(400, "Ungültige Paketversion")
    key = v300._publisher_key(package["publisher_fingerprint"])
    filename = f"{package['plugin_id']}_{package['version']}.tar.gz"
    target = v300.PLUGIN_UPLOADS / filename
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=v300.PLUGIN_UPLOADS, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        total = 0
        try:
            with _open_https(package["package_url"], 60) as response:
                length = int(response.headers.get("Content-Length", "0") or 0)
                if length > v300.MAX_PACKAGE:
                    raise HTTPException(413, "Plugin-Paket ist zu groß")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > v300.MAX_PACKAGE:
                        raise HTTPException(413, "Plugin-Paket ist zu groß")
                    digest.update(chunk)
                    tmp.write(chunk)
            if digest.hexdigest() != package["sha256"]:
                raise HTTPException(400, "SHA256-Prüfung fehlgeschlagen")
            v300._verify_signature(key, bytes.fromhex(package["sha256"]), package["signature"])
            os.chmod(tmp_path, 0o640)
            tmp_path.replace(target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    return target


v300._https_json = _https_json
v300._sync_catalog = _sync_catalog
v300._download_package = _download_package
