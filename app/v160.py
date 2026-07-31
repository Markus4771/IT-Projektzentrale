from __future__ import annotations

"""Version 1.6.0: App-Store-Kataloge und automatische Manifest-Übernahme."""

import json
import sqlite3
import urllib.parse
from typing import Any

import yaml
from fastapi import File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v150 import MAX_MANIFEST_BYTES, app, validate_manifest, _upsert_manifest

VERSION = "1.6.0"
base.VERSION = VERSION
app.version = VERSION
MAX_CATALOG_BYTES = 2 * 1024 * 1024


def init_store_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_catalogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1',
                description TEXT NOT NULL DEFAULT '',
                trusted INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                source_name TEXT NOT NULL DEFAULT 'upload',
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS app_catalog_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_id INTEGER NOT NULL,
                plugin_key TEXT NOT NULL,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Allgemein',
                description TEXT NOT NULL DEFAULT '',
                manifest_json TEXT NOT NULL,
                available INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(catalog_id, plugin_key),
                FOREIGN KEY(catalog_id) REFERENCES app_catalogs(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_catalog_entries_available
              ON app_catalog_entries(available, category, name);
            """
        )


@app.on_event("startup")
def initialize_v160() -> None:
    init_store_db()


def validate_catalog(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Der Katalog muss ein YAML-Objekt sein")
    catalog = data.get("catalog") if isinstance(data.get("catalog"), dict) else data
    key = str(catalog.get("id") or "").strip().lower()
    name = str(catalog.get("name") or "").strip()
    version = str(catalog.get("version") or "1").strip()
    description = str(catalog.get("description") or "").strip()[:2000]
    if not key or len(key) > 64 or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for ch in key):
        raise ValueError("Ungültige Katalog-ID")
    if len(name) < 2 or len(name) > 120:
        raise ValueError("Ungültiger Katalogname")
    raw_apps = data.get("apps") or catalog.get("apps") or []
    if not isinstance(raw_apps, list):
        raise ValueError("apps muss eine Liste sein")
    if len(raw_apps) > 500:
        raise ValueError("Ein Katalog darf höchstens 500 Apps enthalten")
    apps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_apps:
        manifest = validate_manifest(raw)
        if manifest["id"] in seen:
            raise ValueError(f"Doppelte App-ID: {manifest['id']}")
        seen.add(manifest["id"])
        apps.append(manifest)
    return {"id": key, "name": name, "version": version[:80], "description": description, "apps": apps}


def upsert_catalog(catalog: dict[str, Any], trusted: bool, source_name: str) -> int:
    with db() as conn:
        cursor = conn.execute(
            """INSERT INTO app_catalogs(catalog_key,name,version,description,trusted,source_name)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(catalog_key) DO UPDATE SET name=excluded.name,version=excluded.version,
               description=excluded.description,trusted=excluded.trusted,source_name=excluded.source_name,
               updated_at=CURRENT_TIMESTAMP RETURNING id""",
            (catalog["id"], catalog["name"], catalog["version"], catalog["description"], int(trusted), source_name[:200]),
        )
        catalog_id = int(cursor.fetchone()[0])
        active_keys = []
        for manifest in catalog["apps"]:
            active_keys.append(manifest["id"])
            conn.execute(
                """INSERT INTO app_catalog_entries(catalog_id,plugin_key,name,version,category,description,manifest_json)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(catalog_id,plugin_key) DO UPDATE SET name=excluded.name,version=excluded.version,
                   category=excluded.category,description=excluded.description,manifest_json=excluded.manifest_json,
                   available=1,updated_at=CURRENT_TIMESTAMP""",
                (catalog_id, manifest["id"], manifest["name"], manifest["version"], manifest["category"],
                 manifest["description"], json.dumps(manifest, ensure_ascii=False, sort_keys=True)),
            )
        if active_keys:
            placeholders = ",".join("?" for _ in active_keys)
            conn.execute(
                f"UPDATE app_catalog_entries SET available=0 WHERE catalog_id=? AND plugin_key NOT IN ({placeholders})",
                (catalog_id, *active_keys),
            )
        else:
            conn.execute("UPDATE app_catalog_entries SET available=0 WHERE catalog_id=?", (catalog_id,))
    return catalog_id


@app.get("/app-store", response_class=HTMLResponse)
def app_store(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        entries = conn.execute(
            """SELECT e.*,c.name catalog_name,c.trusted catalog_trusted,
               p.id installed_plugin_id,p.enabled plugin_enabled,p.version installed_manifest_version,
               pr.install_status
               FROM app_catalog_entries e
               JOIN app_catalogs c ON c.id=e.catalog_id AND c.enabled=1
               LEFT JOIN plugins p ON p.plugin_key=e.plugin_key
               LEFT JOIN projects pr ON pr.id=p.project_id
               WHERE e.available=1
               ORDER BY e.category,e.name"""
        ).fetchall()
        catalogs = conn.execute(
            """SELECT c.*,COUNT(e.id) app_count FROM app_catalogs c
               LEFT JOIN app_catalog_entries e ON e.catalog_id=c.id AND e.available=1
               GROUP BY c.id ORDER BY c.name"""
        ).fetchall()
    return render("app_store.html", request, entries=entries, catalogs=catalogs,
                  message=message, error=error, title="App Store")


@app.post("/app-store/catalogs/import")
async def import_catalog(request: Request, catalog: UploadFile = File(...), trusted: str | None = None):
    require_admin(request)
    filename = catalog.filename or "catalog.yaml"
    if not filename.lower().endswith((".yaml", ".yml")):
        raise HTTPException(400, "Nur YAML-Kataloge sind erlaubt")
    content = await catalog.read(MAX_CATALOG_BYTES + 1)
    if len(content) > MAX_CATALOG_BYTES:
        raise HTTPException(413, "Der Katalog ist zu groß")
    try:
        clean = validate_catalog(yaml.safe_load(content.decode("utf-8")))
        catalog_id = upsert_catalog(clean, bool(trusted), filename)
    except (UnicodeDecodeError, yaml.YAMLError, ValueError, sqlite3.Error) as exc:
        return RedirectResponse(f"/app-store?error={urllib.parse.quote(str(exc)[:900])}", 303)
    audit("catalog.imported", None, f"{clean['id']} #{catalog_id}, {len(clean['apps'])} Apps")
    return RedirectResponse("/app-store?message=App-Katalog+wurde+importiert", 303)


@app.post("/app-store/apps/{entry_id}/add")
def add_catalog_app(entry_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        entry = conn.execute(
            """SELECT e.*,c.trusted catalog_trusted FROM app_catalog_entries e
               JOIN app_catalogs c ON c.id=e.catalog_id WHERE e.id=? AND e.available=1 AND c.enabled=1""",
            (entry_id,),
        ).fetchone()
    if not entry:
        raise HTTPException(404, "App nicht gefunden")
    try:
        manifest = validate_manifest(json.loads(entry["manifest_json"]))
        plugin_id = _upsert_manifest(manifest, trusted=bool(entry["catalog_trusted"]))
    except (ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        return RedirectResponse(f"/app-store?error={urllib.parse.quote(str(exc)[:900])}", 303)
    audit("catalog.app.added", None, f"{manifest['id']} plugin #{plugin_id}")
    return RedirectResponse("/software-center?message=App+wurde+in+das+Software-Center+übernommen", 303)


@app.post("/app-store/catalogs/{catalog_id}/toggle")
def toggle_catalog(catalog_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        row = conn.execute("SELECT * FROM app_catalogs WHERE id=?", (catalog_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Katalog nicht gefunden")
        enabled = 0 if row["enabled"] else 1
        conn.execute("UPDATE app_catalogs SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (enabled, catalog_id))
    audit("catalog.toggled", None, f"{row['catalog_key']} enabled={enabled}")
    return RedirectResponse("/app-store?message=Katalog-Status+wurde+geändert", 303)


@app.get("/api/v1/app-store")
def app_store_api(request: Request):
    require_user(request)
    with db() as conn:
        rows = conn.execute(
            """SELECT e.id,e.plugin_key,e.name,e.version,e.category,e.description,c.name catalog_name,
               c.trusted,p.id plugin_id,p.enabled plugin_enabled
               FROM app_catalog_entries e JOIN app_catalogs c ON c.id=e.catalog_id
               LEFT JOIN plugins p ON p.plugin_key=e.plugin_key
               WHERE e.available=1 AND c.enabled=1 ORDER BY e.category,e.name"""
        ).fetchall()
    return [dict(row) for row in rows]
