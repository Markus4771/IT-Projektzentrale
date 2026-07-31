from __future__ import annotations

"""Version 3.2.0: standardisiertes Projektmanifest und automatische Erkennung."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v311 import app

VERSION = "3.2.0"
base.VERSION = VERSION
app.version = VERSION

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+~][A-Za-z0-9._-]+)?$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]{1,119}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ALLOWED_TYPES = {"deb", "compose", "script", "plugin", "external"}
ALLOWED_CHANNELS = {"stable", "beta", "development"}
ALLOWED_PROVIDERS = {"github", "gitea", "local"}
ALLOWED_PERMISSIONS = {
    "network", "filesystem-read", "filesystem-write", "database-read",
    "database-write", "notifications", "server-status", "systemd", "docker",
}
MAX_MANIFEST_BYTES = 256 * 1024
MAX_DEPENDENCIES = 64
MAX_PERMISSIONS = 32
DEFAULT_SCAN_ROOTS = ("/srv/itpz-projects", "/opt/itpz-projects")


class ManifestError(ValueError):
    pass


def init_project_framework_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS project_manifests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            project_type TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'stable',
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            package_name TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT '',
            repository TEXT NOT NULL DEFAULT '',
            homepage TEXT NOT NULL DEFAULT '',
            manifest_path TEXT NOT NULL DEFAULT '',
            manifest_sha256 TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            valid INTEGER NOT NULL DEFAULT 1,
            validation_error TEXT NOT NULL DEFAULT '',
            discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS project_manifest_dependencies (
            manifest_id INTEGER NOT NULL,
            dependency_key TEXT NOT NULL,
            version_constraint TEXT NOT NULL DEFAULT '',
            optional INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(manifest_id, dependency_key),
            FOREIGN KEY(manifest_id) REFERENCES project_manifests(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS project_manifest_permissions (
            manifest_id INTEGER NOT NULL,
            permission TEXT NOT NULL,
            PRIMARY KEY(manifest_id, permission),
            FOREIGN KEY(manifest_id) REFERENCES project_manifests(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS project_discovery_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            scanned INTEGER NOT NULL DEFAULT 0,
            imported INTEGER NOT NULL DEFAULT 0,
            rejected INTEGER NOT NULL DEFAULT 0,
            output TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_project_manifests_type ON project_manifests(project_type,enabled);
        CREATE INDEX IF NOT EXISTS idx_project_manifests_channel ON project_manifests(channel,enabled);
        CREATE INDEX IF NOT EXISTS idx_project_discovery_runs_created ON project_discovery_runs(id DESC);
        """)


@app.on_event("startup")
def initialize_v320() -> None:
    init_project_framework_db()


def _text(value: Any, field: str, maximum: int = 500) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ManifestError(f"{field} muss Text sein")
    value = value.strip()
    if len(value) > maximum:
        raise ManifestError(f"{field} ist zu lang")
    return value


def _validate_manifest(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManifestError("Das Manifest muss ein YAML-Objekt sein")
    allowed = {
        "schema", "id", "name", "version", "type", "channel", "description",
        "category", "homepage", "package", "source", "install", "health",
        "dependencies", "permissions", "metadata",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ManifestError("Unbekannte Felder: " + ", ".join(sorted(unknown)))
    if _text(raw.get("schema", "itpz/v1"), "schema", 32) != "itpz/v1":
        raise ManifestError("Nur das Schema itpz/v1 wird unterstützt")

    project_key = _text(raw.get("id"), "id", 63).lower()
    name = _text(raw.get("name"), "name", 120)
    version = _text(raw.get("version"), "version", 64)
    project_type = _text(raw.get("type"), "type", 32).lower()
    channel = _text(raw.get("channel", "stable"), "channel", 32).lower()
    if not ID_RE.fullmatch(project_key):
        raise ManifestError("id muss aus Kleinbuchstaben, Zahlen und Bindestrichen bestehen")
    if len(name) < 2:
        raise ManifestError("name fehlt oder ist zu kurz")
    if not VERSION_RE.fullmatch(version):
        raise ManifestError("version hat kein unterstütztes Format")
    if project_type not in ALLOWED_TYPES:
        raise ManifestError("Unbekannter Projekttyp")
    if channel not in ALLOWED_CHANNELS:
        raise ManifestError("Unbekannter Release-Kanal")

    package = raw.get("package") or {}
    source = raw.get("source") or {}
    install = raw.get("install") or {}
    health = raw.get("health") or {}
    if not all(isinstance(v, dict) for v in (package, source, install, health)):
        raise ManifestError("package, source, install und health müssen Objekte sein")
    package_name = _text(package.get("name", ""), "package.name", 120)
    if package_name and not PACKAGE_RE.fullmatch(package_name):
        raise ManifestError("package.name ist kein gültiger Debian-Paketname")
    provider = _text(source.get("provider", "local"), "source.provider", 32).lower()
    repository = _text(source.get("repository", ""), "source.repository", 200)
    if provider not in ALLOWED_PROVIDERS:
        raise ManifestError("source.provider ist nicht erlaubt")
    if provider in {"github", "gitea"} and not REPOSITORY_RE.fullmatch(repository):
        raise ManifestError("source.repository muss Eigentümer/Repository enthalten")

    dependencies_raw = raw.get("dependencies") or []
    if not isinstance(dependencies_raw, list) or len(dependencies_raw) > MAX_DEPENDENCIES:
        raise ManifestError("dependencies muss eine Liste mit höchstens 64 Einträgen sein")
    dependencies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in dependencies_raw:
        if isinstance(entry, str):
            dep_id, constraint, optional = entry, "", False
        elif isinstance(entry, dict) and not set(entry) - {"id", "version", "optional"}:
            dep_id, constraint, optional = entry.get("id"), entry.get("version", ""), bool(entry.get("optional", False))
        else:
            raise ManifestError("Ungültiger Abhängigkeitseintrag")
        dep_id = _text(dep_id, "dependencies.id", 63).lower()
        constraint = _text(constraint, "dependencies.version", 64)
        if not ID_RE.fullmatch(dep_id) or dep_id == project_key or dep_id in seen:
            raise ManifestError("Ungültige, doppelte oder direkte zyklische Abhängigkeit")
        seen.add(dep_id)
        dependencies.append({"id": dep_id, "version": constraint, "optional": optional})

    permissions_raw = raw.get("permissions") or []
    if not isinstance(permissions_raw, list) or len(permissions_raw) > MAX_PERMISSIONS:
        raise ManifestError("permissions muss eine Liste mit höchstens 32 Einträgen sein")
    permissions: list[str] = []
    for value in permissions_raw:
        permission = _text(value, "permissions", 64).lower()
        if permission not in ALLOWED_PERMISSIONS:
            raise ManifestError(f"Unbekannte Berechtigung: {permission}")
        if permission not in permissions:
            permissions.append(permission)

    return {
        "schema": "itpz/v1", "id": project_key, "name": name, "version": version,
        "type": project_type, "channel": channel,
        "description": _text(raw.get("description", ""), "description", 2000),
        "category": _text(raw.get("category", "Allgemein"), "category", 80) or "Allgemein",
        "homepage": _text(raw.get("homepage", ""), "homepage", 500),
        "package": {"name": package_name, **{k: v for k, v in package.items() if k != "name"}},
        "source": {"provider": provider, "repository": repository, **{k: v for k, v in source.items() if k not in {"provider", "repository"}}},
        "install": install, "health": health, "dependencies": dependencies,
        "permissions": permissions,
        "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
    }


def _parse_manifest_text(text: str) -> tuple[dict[str, Any], str]:
    encoded = text.encode("utf-8")
    if not encoded or len(encoded) > MAX_MANIFEST_BYTES:
        raise ManifestError("Manifest ist leer oder größer als 256 KiB")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"YAML kann nicht gelesen werden: {exc}") from exc
    return _validate_manifest(raw), hashlib.sha256(encoded).hexdigest()


def _store_manifest(manifest: dict[str, Any], digest: str, path: str) -> int:
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO project_manifests(
                   project_key,name,version,project_type,channel,description,category,
                   package_name,provider,repository,homepage,manifest_path,manifest_sha256,manifest_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(project_key) DO UPDATE SET
                   name=excluded.name,version=excluded.version,project_type=excluded.project_type,
                   channel=excluded.channel,description=excluded.description,category=excluded.category,
                   package_name=excluded.package_name,provider=excluded.provider,repository=excluded.repository,
                   homepage=excluded.homepage,manifest_path=excluded.manifest_path,
                   manifest_sha256=excluded.manifest_sha256,manifest_json=excluded.manifest_json,
                   valid=1,validation_error='',updated_at=CURRENT_TIMESTAMP""",
            (manifest["id"], manifest["name"], manifest["version"], manifest["type"], manifest["channel"],
             manifest["description"], manifest["category"], manifest["package"]["name"],
             manifest["source"]["provider"], manifest["source"]["repository"], manifest["homepage"],
             path, digest, json.dumps(manifest, ensure_ascii=False, sort_keys=True)),
        )
        manifest_id = int(conn.execute("SELECT id FROM project_manifests WHERE project_key=?", (manifest["id"],)).fetchone()["id"])
        conn.execute("DELETE FROM project_manifest_dependencies WHERE manifest_id=?", (manifest_id,))
        conn.execute("DELETE FROM project_manifest_permissions WHERE manifest_id=?", (manifest_id,))
        conn.executemany(
            "INSERT INTO project_manifest_dependencies(manifest_id,dependency_key,version_constraint,optional) VALUES(?,?,?,?)",
            [(manifest_id, d["id"], d["version"], int(d["optional"])) for d in manifest["dependencies"]],
        )
        conn.executemany(
            "INSERT INTO project_manifest_permissions(manifest_id,permission) VALUES(?,?)",
            [(manifest_id, p) for p in manifest["permissions"]],
        )
    audit("project_manifest.imported", manifest_id, f"{manifest['id']}:{manifest['version']}")
    return manifest_id


def _scan_roots() -> list[Path]:
    values = os.getenv("ITPZ_PROJECT_SCAN_ROOTS", ":".join(DEFAULT_SCAN_ROOTS)).split(":")
    roots: list[Path] = []
    for value in values:
        path = Path(value.strip())
        if value.strip() and path.is_absolute() and path not in roots:
            roots.append(path)
    return roots[:8]


def _discover(user_id: int | None) -> dict[str, int]:
    scanned = imported = rejected = 0
    messages: list[str] = []
    for root in _scan_roots():
        if not root.is_dir():
            messages.append(f"Übersprungen: {root}")
            continue
        for path in sorted(root.glob("*/projekt.yaml"))[:1000]:
            scanned += 1
            try:
                manifest, digest = _parse_manifest_text(path.read_text(encoding="utf-8"))
                _store_manifest(manifest, digest, str(path))
                imported += 1
                messages.append(f"Importiert: {manifest['id']} {manifest['version']}")
            except (OSError, UnicodeError, ManifestError) as exc:
                rejected += 1
                messages.append(f"Abgelehnt: {path}: {exc}")
    with db() as conn:
        conn.execute(
            "INSERT INTO project_discovery_runs(source,scanned,imported,rejected,output,created_by) VALUES(?,?,?,?,?,?)",
            (":".join(str(p) for p in _scan_roots()), scanned, imported, rejected, "\n".join(messages)[-20000:], user_id),
        )
    return {"scanned": scanned, "imported": imported, "rejected": rejected}


def _summary() -> dict[str, Any]:
    with db() as conn:
        manifests = [dict(r) for r in conn.execute("SELECT * FROM project_manifests ORDER BY name")]
        runs = [dict(r) for r in conn.execute(
            "SELECT r.*,u.username created_by_name FROM project_discovery_runs r LEFT JOIN users u ON u.id=r.created_by ORDER BY r.id DESC LIMIT 30"
        )]
        known = {r["project_key"] for r in conn.execute("SELECT project_key FROM project_manifests WHERE enabled=1 AND valid=1")}
        for manifest in manifests:
            deps = [dict(r) for r in conn.execute(
                "SELECT dependency_key,version_constraint,optional FROM project_manifest_dependencies WHERE manifest_id=? ORDER BY dependency_key",
                (manifest["id"],),
            )]
            manifest["dependencies"] = deps
            manifest["permissions"] = [r["permission"] for r in conn.execute(
                "SELECT permission FROM project_manifest_permissions WHERE manifest_id=? ORDER BY permission", (manifest["id"],)
            )]
            manifest["missing_dependencies"] = [d["dependency_key"] for d in deps if not d["optional"] and d["dependency_key"] not in known]
    return {"manifests": manifests, "runs": runs, "scan_roots": [str(p) for p in _scan_roots()]}


@app.get("/project-framework", response_class=HTMLResponse)
def project_framework(request: Request, message: str = "", error: str = ""):
    require_user(request)
    return render("project_framework.html", request, title="Projekt-Framework", message=message, error=error, **_summary())


@app.post("/project-framework/import")
def import_project_manifest(request: Request, manifest_yaml: str = Form(...)):
    user = require_admin(request)
    try:
        manifest, digest = _parse_manifest_text(manifest_yaml)
        _store_manifest(manifest, digest, "Web-Import")
    except ManifestError as exc:
        return RedirectResponse("/project-framework?error=" + quote(str(exc)), 303)
    audit("project_manifest.web_import", None, f"user={user['id']}")
    return RedirectResponse("/project-framework?message=Manifest+wurde+importiert", 303)


@app.post("/project-framework/discover")
def discover_project_manifests(request: Request):
    user = require_admin(request)
    result = _discover(user["id"])
    audit("project_manifest.discovery", None, json.dumps(result))
    return RedirectResponse(f"/project-framework?message={result['imported']}+importiert,+{result['rejected']}+abgelehnt", 303)


@app.post("/project-framework/{manifest_id}/toggle")
def toggle_project_manifest(manifest_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        row = conn.execute("SELECT enabled FROM project_manifests WHERE id=?", (manifest_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Manifest nicht gefunden")
        conn.execute("UPDATE project_manifests SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (0 if row["enabled"] else 1, manifest_id))
    return RedirectResponse("/project-framework?message=Status+wurde+geändert", 303)


@app.post("/project-framework/{manifest_id}/apply")
def apply_project_manifest(manifest_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        row = conn.execute("SELECT manifest_json FROM project_manifests WHERE id=? AND enabled=1 AND valid=1", (manifest_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Aktives Manifest nicht gefunden")
        missing = [r["dependency_key"] for r in conn.execute(
            """SELECT d.dependency_key FROM project_manifest_dependencies d
               LEFT JOIN project_manifests m ON m.project_key=d.dependency_key AND m.enabled=1 AND m.valid=1
               WHERE d.manifest_id=? AND d.optional=0 AND m.id IS NULL""", (manifest_id,)
        )]
        if missing:
            return RedirectResponse("/project-framework?error=" + quote("Fehlende Abhängigkeiten: " + ", ".join(missing)), 303)
        manifest = json.loads(row["manifest_json"])
        repository = manifest["source"]["repository"]
        repo_url = f"https://github.com/{repository}" if manifest["source"]["provider"] == "github" and repository else ""
        project = conn.execute("SELECT id FROM projects WHERE slug=? AND deleted_at IS NULL", (manifest["id"],)).fetchone()
        if project:
            project_id = int(project["id"])
            conn.execute(
                """UPDATE projects SET name=?,description=?,category=?,version=?,project_url=?,repo_url=?,package_name=? WHERE id=?""",
                (manifest["name"], manifest["description"], manifest["category"], manifest["version"], manifest["homepage"], repo_url, manifest["package"]["name"], project_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO projects(name,slug,description,category,status,version,project_url,repo_url,package_name)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (manifest["name"], manifest["id"], manifest["description"], manifest["category"], "Geplant", manifest["version"], manifest["homepage"], repo_url, manifest["package"]["name"]),
            )
            project_id = int(cursor.lastrowid)
        if manifest["source"]["provider"] in {"github", "gitea"}:
            base_url = "https://github.com" if manifest["source"]["provider"] == "github" else _text(manifest["source"].get("base_url", ""), "source.base_url", 500)
            conn.execute(
                """INSERT INTO package_sources(project_id,provider,base_url,repository,token,asset_pattern,enabled)
                   VALUES(?,?,?,?, '',?,1) ON CONFLICT(project_id) DO UPDATE SET
                   provider=excluded.provider,base_url=excluded.base_url,repository=excluded.repository,
                   asset_pattern=excluded.asset_pattern,enabled=1,last_error=''""",
                (project_id, manifest["source"]["provider"], base_url, repository, _text(manifest["package"].get("asset", "*.deb"), "package.asset", 200) or "*.deb"),
            )
    audit("project_manifest.applied", project_id, manifest["id"])
    return RedirectResponse("/project-framework?message=Manifest+wurde+in+den+Projektkatalog+übernommen", 303)


@app.get("/api/v1/project-framework")
def project_framework_api(request: Request):
    require_user(request)
    summary = _summary()
    return {
        "version": VERSION, "schema": "itpz/v1", "scan_roots": summary["scan_roots"],
        "manifests": [{
            "id": m["project_key"], "name": m["name"], "version": m["version"],
            "type": m["project_type"], "channel": m["channel"], "enabled": bool(m["enabled"]),
            "valid": bool(m["valid"]), "sha256": m["manifest_sha256"],
            "dependencies": m["dependencies"], "missing_dependencies": m["missing_dependencies"],
            "permissions": m["permissions"], "source": {"provider": m["provider"], "repository": m["repository"]},
        } for m in summary["manifests"]],
    }
