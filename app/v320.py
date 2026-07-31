from __future__ import annotations

"""Version 3.2.0: standardisiertes Projektmanifest und automatische Erkennung."""

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

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


def _clean_text(value: Any, field: str, maximum: int = 500) -> str:
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
    unknown = set(raw) - {
        "schema", "id", "name", "version", "type", "channel", "description",
        "category", "homepage", "package", "source", "install", "health",
        "dependencies", "permissions", "metadata",
    }
    if unknown:
        raise ManifestError("Unbekannte Felder: " + ", ".join(sorted(unknown)))

    schema = _clean_text(raw.get("schema", "itpz/v1"), "schema", 32)
    if schema != "itpz/v1":
        raise ManifestError("Nur das Schema itpz/v1 wird unterstützt")
    project_key = _clean_text(raw.get("id"), "id", 63).lower()
    if not ID_RE.fullmatch(project_key):
        raise ManifestError("id muss aus Kleinbuchstaben, Zahlen und Bindestrichen bestehen")
    name = _clean_text(raw.get("name"), "name", 120)
    if len(name) < 2:
        raise ManifestError("name fehlt oder ist zu kurz")
    version = _clean_text(raw.get("version"), "version", 64)
    if not VERSION_RE.fullmatch(version):
        raise ManifestError("version hat kein unterstütztes Format")
    project_type = _clean_text(raw.get("type"), "type", 32).lower()
    if project_type not in ALLOWED_TYPES:
        raise ManifestError("Unbekannter Projekttyp")
    channel = _clean_text(raw.get("channel", "stable"), "channel", 32).lower()
    if channel not in ALLOWED_CHANNELS:
        raise ManifestError("Unbekannter Release-Kanal")

    package = raw.get("package") or {}
    if not isinstance(package, dict):
        raise ManifestError("package muss ein Objekt sein")
    package_name = _clean_text(package.get("name", ""), "package.name", 120)
    if package_name and not PACKAGE_RE.fullmatch(package_name):
        raise ManifestError("package.name ist kein gültiger Debian-Paketname")

    source = raw.get("source") or {}
    if not isinstance(source, dict):
        raise ManifestError("source muss ein Objekt sein")
    provider = _clean_text(source.get("provider", "local"), "source.provider", 32).lower()
    if provider not in ALLOWED_PROVIDERS:
        raise ManifestError("source.provider ist nicht erlaubt")
    repository = _clean_text(source.get("repository", ""), "source.repository", 200)
    if provider in {"github", "gitea"} and not REPOSITORY_RE.fullmatch(repository):
        raise ManifestError("source.repository muss Eigentümer/Repository enthalten")

    dependencies_raw = raw.get("dependencies") or []
    if not isinstance(dependencies_raw, list) or len(dependencies_raw) > MAX_DEPENDENCIES:
        raise ManifestError("dependencies muss eine Liste mit höchstens 64 Einträgen sein")
    dependencies: list[dict[str, Any]] = []
    seen_dependencies: set[str] = set()
    for entry in dependencies_raw:
        if isinstance(entry, str):
            dep_key, constraint, optional = entry, "", False
        elif isinstance(entry, dict):
            dep_key = entry.get("id")
            constraint = entry.get("version", "")
            optional = bool(entry.get("optional", False))
            if set(entry) - {"id", "version", "optional"}:
                raise ManifestError("Eine Abhängigkeit enthält unbekannte Felder")
        else:
            raise ManifestError("Ungültiger Abhängigkeitseintrag")
        dep_key = _clean_text(dep_key, "dependencies.id", 63).lower()
        constraint = _clean_text(constraint, "dependencies.version", 64)
        if not ID_RE.fullmatch(dep_key) or dep_key == project_key:
            raise ManifestError("Ungültige oder zyklische direkte Abhängigkeit")
        if dep_key in seen_dependencies:
            raise ManifestError("Abhängigkeit ist doppelt vorhanden")
        seen_dependencies.add(dep_key)
        dependencies.append({"id": dep_key, "version": constraint, "optional": optional})

    permissions_raw = raw.get("permissions") or []
    if not isinstance(permissions_raw, list) or len(permissions_raw) > MAX_PERMISSIONS:
        raise ManifestError("permissions muss eine Liste mit höchstens 32 Einträgen sein")
    permissions: list[str] = []
    for permission in permissions_raw:
        permission = _clean_text(permission, "permissions", 64).lower()
        if permission not in ALLOWED_PERMISSIONS:
            raise ManifestError(f"Unbekannte Berechtigung: {permission}")
        if permission not in permissions:
            permissions.append(permission)

    install = raw.get("install") or {}
    health = raw.get("health") or {}
    if not isinstance(install, dict) or not isinstance(health, dict):
        raise ManifestError("install und health müssen Objekte sein")

    return {
        "schema": schema,
        "id": project_key,
        "name": name,
        "version": version,
        "type": project_type,
        "channel": channel,
        "description": _clean_text(raw.get("description", ""), "description", 2000),
        "category": _clean_text(raw.get("category", ""), "category", 80),
        "homepage": _clean_text(raw.get("homepage", ""), "homepage", 500),
        "package": {"name": package_name, **{k: v for k, v in package.items() if k != "name"}},
        "source": {"provider": provider, "repository": repository, **{k: v for k, v in source.items() if k not in {"provider", "repository"}}},
        "install": install,
        "health": health,
        "dependencies": dependencies,
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
    normalized = _validate_manifest(raw)
    digest = hashlib.sha256(encoded).hexdigest()
    return normalized, digest


def _store_manifest(manifest: dict[str, Any], digest: str, path: str, user_id: int | None) -> int:
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO project_manifests(
                   project_key,name,version,project_type,channel,description,category,
                   package_name,provider,repository,homepage,manifest_path,manifest_sha256,manifest_json,
                   enabled,valid,validation_error,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,1,'',CURRENT_TIMESTAMP)
               ON CONFLICT(project_key) DO UPDATE SET
                   name=excluded.name,version=excluded.version,project_type=excluded.project_type,
                   channel=excluded.channel,description=excluded.description,category=excluded.category,
                   package_name=excluded.package_name,provider=excluded.provider,repository=excluded.repository,
                   homepage=excluded.homepage,manifest_path=excluded.manifest_path,
                   manifest_sha256=excluded.manifest_sha256,manifest_json=excluded.manifest_json,
                   valid=1,validation_error='',updated_at=CURRENT_TIMESTAMP""",
            (
                manifest["id"], manifest["name"], manifest["version"], manifest["type"], manifest["channel"],
                manifest["description"], manifest["category"], manifest["package"]["name"],
                manifest["source"]["provider"], manifest["source"]["repository"], manifest["homepage"],
                path, digest, json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            ),
        )
        manifest_id = int(conn.execute(
            "SELECT id FROM project_manifests WHERE project_key=?", (manifest["id"],)
        ).fetchone()["id"])
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
    configured = os.getenv("ITPZ_PROJECT_SCAN_ROOTS", ":".join(DEFAULT_SCAN_ROOTS))
    roots: list[Path] = []
    for value in configured.split(":"):
        value = value.strip()
        if not value:
            continue
        path = Path(value)
        if path.is_absolute() and path not in roots:
            roots.append(path)
    return roots[:8]


def _discover(user_id: int | None) -> dict[str, Any]:
    scanned = imported = rejected = 0
    messages: list[str] = []
    for root in _scan_roots():
        if not root.is_dir():
            messages.append(f"Übersprungen: {root}")
            continue
        for path in sorted(root.glob("*/projekt.yaml"))[:1000]:
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8")
                manifest, digest = _parse_manifest_text(text)
                _store_manifest(manifest, digest, str(path), user_id)
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
    return {"scanned": scanned, "imported": imported, "rejected": rejected, "messages": messages}


def _framework_summary() -> dict[str, Any]:
    with db() as conn:
        manifests = [dict(row) for row in conn.execute(
            """SELECT m.*,
                      (SELECT COUNT(*) FROM project_manifest_dependencies d WHERE d.manifest_id=m.id) dependency_count,
                      (SELECT COUNT(*) FROM project_manifest_permissions p WHERE p.manifest_id=m.id) permission_count
               FROM project_manifests m ORDER BY m.name"""
        )]
        runs = [dict(row) for row in conn.execute(
            """SELECT r.*,u.username AS created_by_name FROM project_discovery_runs r
               LEFT JOIN users u ON u.id=r.created_by ORDER BY r.id DESC LIMIT 30"""
        )]
        known_keys = {row["project_key"] for row in conn.execute("SELECT project_key FROM project_manifests WHERE enabled=1 AND valid=1")}
        for manifest in manifests:
            dependencies = [dict(row) for row in conn.execute(
                "SELECT dependency_key,version_constraint,optional FROM project_manifest_dependencies WHERE manifest_id=? ORDER BY dependency_key",
                (manifest["id"],),
            )]
            permissions = [row["permission"] for row in conn.execute(
                "SELECT permission FROM project_manifest_permissions WHERE manifest_id=? ORDER BY permission",
                (manifest["id"],),
            )]
            manifest["dependencies"] = dependencies
            manifest["permissions"] = permissions
            manifest["missing_dependencies"] = [d["dependency_key"] for d in dependencies if not d["optional"] and d["dependency_key"] not in known_keys]
    return {"manifests": manifests, "runs": runs, "scan_roots": [str(p) for p in _scan_roots()]}


@app.get("/project-framework", response_class=HTMLResponse)
def project_framework(request: Request, message: str = "", error: str = ""):
    require_user(request)
    return render("project_framework.html", request, title="Projekt-Framework", message=message, error=error, **_framework_summary())


@app.post("/project-framework/import")
def import_project_manifest(request: Request, manifest_yaml: str = Form(...)):
    user = require_admin(request)
    try:
        manifest, digest = _parse_manifest_text(manifest_yaml)
        _store_manifest(manifest, digest, "Web-Import", user["id"])
    except ManifestError as exc:
        return RedirectResponse("/project-framework?error=" + str(exc).replace(" ", "+"), 303)
    return RedirectResponse("/project-framework?message=Manifest+wurde+importiert", 303)


@app.post("/project-framework/discover")
def discover_project_manifests(request: Request):
    user = require_admin(request)
    result = _discover(user["id"])
    audit("project_manifest.discovery", None, json.dumps({k: result[k] for k in ("scanned", "imported", "rejected")}))
    return RedirectResponse(
        f"/project-framework?message={result['imported']}+importiert,+{result['rejected']}+abgelehnt", 303
    )


@app.post("/project-framework/{manifest_id}/toggle")
def toggle_project_manifest(manifest_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        row = conn.execute("SELECT enabled FROM project_manifests WHERE id=?", (manifest_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Manifest nicht gefunden")
        conn.execute("UPDATE project_manifests SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (0 if row["enabled"] else 1, manifest_id))
    audit("project_manifest.toggled", manifest_id, "")
    return RedirectResponse("/project-framework?message=Status+wurde+geändert", 303)


@app.post("/project-framework/{manifest_id}/apply")
def apply_project_manifest(manifest_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        row = conn.execute("SELECT * FROM project_manifests WHERE id=? AND enabled=1 AND valid=1", (manifest_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Aktives Manifest nicht gefunden")
        manifest = json.loads(row["manifest_json"])
        missing = conn.execute(
            """SELECT d.dependency_key FROM project_manifest_dependencies d
               LEFT JOIN project_manifests m ON m.project_key=d.dependency_key AND m.enabled=1 AND m.valid=1
               WHERE d.manifest_id=? AND d.optional=0 AND m.id IS NULL""",
            (manifest_id,),
        ).fetchall()
        if missing:
            names = ", ".join(r["dependency_key"] for r in missing)
            return RedirectResponse("/project-framework?error=Fehlende+Abhängigkeiten:++" + names.replace(" ", "+"), 303)
        project = conn.execute("SELECT id FROM projects WHERE name=? AND deleted_at IS NULL", (manifest["name"],)).fetchone()
        if project:
            project_id = int(project["id"])
            conn.execute(
                """UPDATE projects SET category=?,description=?,package_name=?,latest_version=?,homepage_url=? WHERE id=?""",
                (manifest["category"], manifest["description"], manifest["package"]["name"], manifest["version"], manifest["homepage"], project_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO projects(name,category,description,package_name,latest_version,homepage_url,status)
                   VALUES(?,?,?,?,?,?,'planned')""",
                (manifest["name"], manifest["category"], manifest["description"], manifest["package"]["name"], manifest["version"], manifest["homepage"]),
            )
            project_id = int(cursor.lastrowid)
        if manifest["source"]["provider"] in {"github", "gitea"}:
            base_url = "https://github.com" if manifest["source"]["provider"] == "github" else ""
            conn.execute(
                """INSERT INTO package_sources(project_id,provider,base_url,repository,token,asset_pattern,enabled)
                   VALUES(?,?,?,?, '',?,1) ON CONFLICT(project_id) DO UPDATE SET
                   provider=excluded.provider,base_url=excluded.base_url,repository=excluded.repository,
                   asset_pattern=excluded.asset_pattern,enabled=1,updated_at=CURRENT_TIMESTAMP""",
                (project_id, manifest["source"]["provider"], base_url, manifest["source"]["repository"], manifest["package"].get("asset", "*.deb")),
            )
    audit("project_manifest.applied", project_id, manifest["id"])
    return RedirectResponse("/project-framework?message=Manifest+wurde+in+den+Projektkatalog+übernommen", 303)


@app.get("/api/v1/project-framework")
def project_framework_api(request: Request):
    require_user(request)
    summary = _framework_summary()
    return {
        "version": VERSION,
        "schema": "itpz/v1",
        "scan_roots": summary["scan_roots"],
        "manifests": [
            {
                "id": m["project_key"], "name": m["name"], "version": m["version"],
                "type": m["project_type"], "channel": m["channel"], "enabled": bool(m["enabled"]),
                "valid": bool(m["valid"]), "sha256": m["manifest_sha256"],
                "dependencies": m["dependencies"], "missing_dependencies": m["missing_dependencies"],
                "permissions": m["permissions"], "source": {"provider": m["provider"], "repository": m["repository"]},
            }
            for m in summary["manifests"]
        ],
    }
