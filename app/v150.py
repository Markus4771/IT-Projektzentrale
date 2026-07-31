from __future__ import annotations

"""Version 1.5.0: deklaratives Plugin-Framework und projekt.yaml-Import."""

import json
import re
import sqlite3
import urllib.parse
from typing import Any

import yaml
from fastapi import File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user, validate_http_url
from app.v140 import app

VERSION = "1.5.0"
base.VERSION = VERSION
app.version = VERSION

PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,63}$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
SERVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@:-]*(?:\.service)?$")
ALLOWED_INSTALL_TYPES = {"deb", "docker", "compose", "external", "manual"}
ALLOWED_CAPABILITIES = {
    "install", "update", "uninstall", "backup", "restore", "health", "settings",
    "dashboard", "logs", "service-control", "api", "webhook",
}
MAX_MANIFEST_BYTES = 512 * 1024


def init_plugin_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plugins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                manifest_version TEXT NOT NULL DEFAULT '1',
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Allgemein',
                author TEXT NOT NULL DEFAULT '',
                license TEXT NOT NULL DEFAULT '',
                icon TEXT NOT NULL DEFAULT '',
                homepage_url TEXT NOT NULL DEFAULT '',
                repository_url TEXT NOT NULL DEFAULT '',
                install_type TEXT NOT NULL DEFAULT 'deb',
                package_name TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                trusted INTEGER NOT NULL DEFAULT 0,
                manifest_json TEXT NOT NULL DEFAULT '{}',
                project_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS plugin_capabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id INTEGER NOT NULL,
                capability TEXT NOT NULL,
                configuration_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(plugin_id, capability),
                FOREIGN KEY(plugin_id) REFERENCES plugins(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_plugins_enabled ON plugins(enabled, category, name);
            """
        )


@app.on_event("startup")
def initialize_v150() -> None:
    init_plugin_db()


def _text(value: Any, *, maximum: int = 500) -> str:
    return str(value or "").strip()[:maximum]


def _url(value: Any, label: str) -> str:
    return validate_http_url(_text(value, maximum=1000), label)


def _capabilities(raw: Any) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if isinstance(raw, list):
        items = {str(item): {} for item in raw}
    elif isinstance(raw, dict):
        items = {str(key): value if isinstance(value, dict) else {} for key, value in raw.items()}
    else:
        raise ValueError("capabilities muss eine Liste oder ein Objekt sein")
    invalid = sorted(set(items) - ALLOWED_CAPABILITIES)
    if invalid:
        raise ValueError("Unbekannte Fähigkeiten: " + ", ".join(invalid))
    return {key: items[key] for key in sorted(items)}


def validate_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Das Manifest muss ein YAML-Objekt enthalten")
    manifest_version = _text(data.get("manifest_version") or data.get("schema") or "1", maximum=20)
    plugin_key = _text(data.get("id"), maximum=64).lower()
    name = _text(data.get("name"), maximum=120)
    version = _text(data.get("version"), maximum=80)
    if not PLUGIN_ID_RE.fullmatch(plugin_key):
        raise ValueError("id: 2 bis 64 Kleinbuchstaben, Zahlen, Punkt, Unterstrich oder Bindestrich")
    if len(name) < 2:
        raise ValueError("name fehlt oder ist zu kurz")
    if not version:
        raise ValueError("version fehlt")

    install = data.get("install") or {}
    if not isinstance(install, dict):
        raise ValueError("install muss ein Objekt sein")
    install_type = _text(install.get("type") or "deb", maximum=20).lower()
    if install_type not in ALLOWED_INSTALL_TYPES:
        raise ValueError("Nicht unterstützter Installationstyp")
    package_name = _text(install.get("package") or data.get("package_name"), maximum=120)
    if install_type == "deb" and package_name and not PACKAGE_RE.fullmatch(package_name):
        raise ValueError("Ungültiger Debian-Paketname")

    services = data.get("services") or []
    if not isinstance(services, list) or len(services) > 20:
        raise ValueError("services muss eine Liste mit höchstens 20 Einträgen sein")
    clean_services: list[str] = []
    for service in services:
        value = _text(service, maximum=120)
        if not SERVICE_RE.fullmatch(value):
            raise ValueError(f"Ungültiger systemd-Dienst: {value}")
        clean_services.append(value if value.endswith(".service") else value + ".service")

    source = data.get("source") or {}
    if not isinstance(source, dict):
        raise ValueError("source muss ein Objekt sein")
    provider = _text(source.get("provider"), maximum=20).lower()
    repository = _text(source.get("repository"), maximum=200)
    base_url = _url(source.get("base_url") or ("https://github.com" if provider == "github" else ""), "Quellserver")
    if provider and provider not in {"github", "gitea"}:
        raise ValueError("source.provider muss github oder gitea sein")
    if repository and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("source.repository muss Eigentümer/Repository enthalten")

    health = data.get("health") or {}
    if not isinstance(health, dict):
        raise ValueError("health muss ein Objekt sein")
    health_url = _url(health.get("url"), "Health-URL")

    return {
        "manifest_version": manifest_version,
        "id": plugin_key,
        "name": name,
        "version": version,
        "description": _text(data.get("description"), maximum=2000),
        "category": _text(data.get("category") or "Allgemein", maximum=100),
        "author": _text(data.get("author"), maximum=150),
        "license": _text(data.get("license"), maximum=100),
        "icon": _text(data.get("icon"), maximum=500),
        "homepage": _url(data.get("homepage"), "Homepage"),
        "repository": _url(data.get("repository"), "Repository"),
        "install": {"type": install_type, "package": package_name},
        "source": {
            "provider": provider,
            "base_url": base_url,
            "repository": repository,
            "asset_pattern": _text(source.get("asset_pattern") or "*.deb", maximum=200),
        },
        "services": sorted(set(clean_services)),
        "health": {"url": health_url},
        "capabilities": _capabilities(data.get("capabilities")),
        "permissions": sorted({_text(item, maximum=80) for item in (data.get("permissions") or []) if _text(item)}),
    }


def _upsert_manifest(manifest: dict[str, Any], trusted: bool) -> int:
    install = manifest["install"]
    source = manifest["source"]
    slug = manifest["id"].replace(".", "-").replace("_", "-")
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE slug=?", (slug,)).fetchone()
        if project:
            project_id = int(project["id"])
            conn.execute(
                """UPDATE projects SET name=?,description=?,category=?,version=?,repo_url=?,homepage_url=?,
                   package_name=?,service_name=?,install_type=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (manifest["name"], manifest["description"], manifest["category"], manifest["version"],
                 manifest["repository"], manifest["homepage"], install["package"],
                 manifest["services"][0] if manifest["services"] else "", install["type"], project_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO projects(name,slug,description,category,status,version,repo_url,homepage_url,
                   package_name,service_name,install_type,install_status)
                   VALUES(?,?,?,?,'In Entwicklung',?,?,?,?,?,?,'not_installed')""",
                (manifest["name"], slug, manifest["description"], manifest["category"], manifest["version"],
                 manifest["repository"], manifest["homepage"], install["package"],
                 manifest["services"][0] if manifest["services"] else "", install["type"]),
            )
            project_id = int(cursor.lastrowid)

        cursor = conn.execute(
            """INSERT INTO plugins(plugin_key,name,version,manifest_version,description,category,author,license,
               icon,homepage_url,repository_url,install_type,package_name,trusted,manifest_json,project_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(plugin_key) DO UPDATE SET name=excluded.name,version=excluded.version,
               manifest_version=excluded.manifest_version,description=excluded.description,category=excluded.category,
               author=excluded.author,license=excluded.license,icon=excluded.icon,homepage_url=excluded.homepage_url,
               repository_url=excluded.repository_url,install_type=excluded.install_type,package_name=excluded.package_name,
               trusted=excluded.trusted,manifest_json=excluded.manifest_json,project_id=excluded.project_id,
               updated_at=CURRENT_TIMESTAMP RETURNING id""",
            (manifest["id"], manifest["name"], manifest["version"], manifest["manifest_version"],
             manifest["description"], manifest["category"], manifest["author"], manifest["license"],
             manifest["icon"], manifest["homepage"], manifest["repository"], install["type"], install["package"],
             int(trusted), json.dumps(manifest, ensure_ascii=False, sort_keys=True), project_id),
        )
        plugin_id = int(cursor.fetchone()[0])
        conn.execute("DELETE FROM plugin_capabilities WHERE plugin_id=?", (plugin_id,))
        for capability, configuration in manifest["capabilities"].items():
            conn.execute(
                "INSERT INTO plugin_capabilities(plugin_id,capability,configuration_json) VALUES(?,?,?)",
                (plugin_id, capability, json.dumps(configuration, ensure_ascii=False, sort_keys=True)),
            )
        conn.execute("DELETE FROM project_services WHERE project_id=?", (project_id,))
        for position, service in enumerate(manifest["services"], start=1):
            conn.execute(
                "INSERT INTO project_services(project_id,service_name,display_name,sort_order) VALUES(?,?,?,?)",
                (project_id, service, service, position * 10),
            )
        if source["provider"] and source["repository"]:
            conn.execute(
                """INSERT INTO package_sources(project_id,provider,base_url,repository,token,asset_pattern,enabled)
                   VALUES(?,?,?,?, '',?,1)
                   ON CONFLICT(project_id) DO UPDATE SET provider=excluded.provider,base_url=excluded.base_url,
                   repository=excluded.repository,asset_pattern=excluded.asset_pattern,enabled=1,last_error=''""",
                (project_id, source["provider"], source["base_url"], source["repository"], source["asset_pattern"]),
            )
    return plugin_id


@app.get("/plugins", response_class=HTMLResponse)
def plugins_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        rows = conn.execute(
            """SELECT pl.*,p.slug,p.install_status,
               GROUP_CONCAT(pc.capability, ', ') capabilities
               FROM plugins pl LEFT JOIN projects p ON p.id=pl.project_id
               LEFT JOIN plugin_capabilities pc ON pc.plugin_id=pl.id
               GROUP BY pl.id ORDER BY pl.category,pl.name"""
        ).fetchall()
    return render("plugins.html", request, plugins=rows, message=message, error=error, title="Plugins")


@app.post("/plugins/import")
async def import_plugin_manifest(request: Request, manifest: UploadFile = File(...), trusted: str | None = None):
    require_admin(request)
    filename = manifest.filename or ""
    if not filename.lower().endswith((".yaml", ".yml")):
        raise HTTPException(400, "Nur YAML-Manifeste sind erlaubt")
    content = await manifest.read(MAX_MANIFEST_BYTES + 1)
    if len(content) > MAX_MANIFEST_BYTES:
        raise HTTPException(413, "Das Manifest ist zu groß")
    try:
        data = yaml.safe_load(content.decode("utf-8"))
        clean = validate_manifest(data)
        plugin_id = _upsert_manifest(clean, trusted=bool(trusted))
    except (UnicodeDecodeError, yaml.YAMLError, ValueError, sqlite3.Error) as exc:
        return RedirectResponse(f"/plugins?error={urllib.parse.quote(str(exc)[:900])}", 303)
    audit("plugin.imported", None, f"{clean['id']} #{plugin_id} v{clean['version']}")
    return RedirectResponse("/plugins?message=Plugin-Manifest+wurde+importiert", 303)


@app.post("/plugins/{plugin_id}/toggle")
def toggle_plugin(plugin_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        plugin = conn.execute("SELECT * FROM plugins WHERE id=?", (plugin_id,)).fetchone()
        if not plugin:
            raise HTTPException(404, "Plugin nicht gefunden")
        enabled = 0 if plugin["enabled"] else 1
        conn.execute("UPDATE plugins SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (enabled, plugin_id))
    audit("plugin.toggled", plugin["project_id"], f"{plugin['plugin_key']} enabled={enabled}")
    return RedirectResponse("/plugins?message=Plugin-Status+wurde+geändert", 303)


@app.get("/api/v1/plugins")
def plugins_api(request: Request):
    require_user(request)
    with db() as conn:
        rows = conn.execute("SELECT * FROM plugins ORDER BY category,name").fetchall()
        capabilities = conn.execute("SELECT * FROM plugin_capabilities ORDER BY plugin_id,capability").fetchall()
    by_plugin: dict[int, list[dict[str, Any]]] = {}
    for row in capabilities:
        by_plugin.setdefault(int(row["plugin_id"]), []).append({
            "capability": row["capability"],
            "configuration": json.loads(row["configuration_json"] or "{}"),
        })
    return [{**dict(row), "manifest": json.loads(row["manifest_json"] or "{}"),
             "capabilities": by_plugin.get(int(row["id"]), [])} for row in rows]
