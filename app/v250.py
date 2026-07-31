from __future__ import annotations

"""Version 2.5.0: sicherer Marketplace und Plugin-Lebenszyklus."""

import json
import re
import subprocess
import urllib.parse
from pathlib import Path

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v240 import app

VERSION = "2.5.0"
base.VERSION = VERSION
app.version = VERSION
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]{0,39}$")
PERMISSIONS = {"network", "filesystem-read", "filesystem-write", "database-read", "database-write", "notifications", "server-status"}
ACTIONS = {"install", "update", "enable", "disable", "remove"}
HELPER = "/usr/lib/it-projektzentrale/itpz-plugin-helper"


def init_marketplace_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS marketplace_publishers (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE,
          public_key TEXT NOT NULL DEFAULT '', trusted INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS marketplace_catalogs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, catalog_url TEXT NOT NULL,
          publisher_id INTEGER, enabled INTEGER NOT NULL DEFAULT 1, last_status TEXT NOT NULL DEFAULT 'never',
          last_error TEXT NOT NULL DEFAULT '', last_synced_at TEXT,
          FOREIGN KEY(publisher_id) REFERENCES marketplace_publishers(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS marketplace_packages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, catalog_id INTEGER, plugin_id TEXT NOT NULL, name TEXT NOT NULL,
          version TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', package_url TEXT NOT NULL DEFAULT '',
          sha256 TEXT NOT NULL, signature TEXT NOT NULL DEFAULT '', publisher_fingerprint TEXT NOT NULL,
          permissions_json TEXT NOT NULL DEFAULT '[]', dependencies_json TEXT NOT NULL DEFAULT '[]',
          manifest_json TEXT NOT NULL DEFAULT '{}', available INTEGER NOT NULL DEFAULT 1,
          UNIQUE(catalog_id,plugin_id,version), FOREIGN KEY(catalog_id) REFERENCES marketplace_catalogs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS installed_plugins (
          id INTEGER PRIMARY KEY AUTOINCREMENT, plugin_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
          version TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, publisher_fingerprint TEXT NOT NULL,
          permissions_json TEXT NOT NULL DEFAULT '[]', dependencies_json TEXT NOT NULL DEFAULT '[]',
          package_sha256 TEXT NOT NULL, installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS plugin_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, plugin_id TEXT NOT NULL, action TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'running', output TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
          created_by INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT,
          FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_plugin_jobs_plugin ON plugin_jobs(plugin_id,id DESC);
        """)


@app.on_event("startup")
def initialize_v250() -> None:
    init_marketplace_db()


def _json_list(value: str, allowed: set[str] | None = None) -> list[str]:
    items = [x.strip() for x in value.split(",") if x.strip()]
    if allowed is not None and any(x not in allowed for x in items):
        raise HTTPException(400, "Nicht erlaubte Plugin-Berechtigung")
    return sorted(set(items))


def _run_helper(action: str, plugin_id: str, package_file: str = "", expected_sha256: str = "") -> dict:
    args = ["/usr/bin/sudo", HELPER, action, plugin_id]
    if action in {"install", "update"}:
        args.extend([Path(package_file).name, expected_sha256])
    result = subprocess.run(args, capture_output=True, text=True, timeout=900, check=False)
    return {"state": "succeeded" if result.returncode == 0 else "failed", "output": result.stdout[-100000:], "error": result.stderr[-100000:]}


@app.get("/marketplace", response_class=HTMLResponse)
def marketplace_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        publishers = [dict(r) for r in conn.execute("SELECT * FROM marketplace_publishers ORDER BY trusted DESC,name")]
        catalogs = [dict(r) for r in conn.execute("SELECT c.*,p.name publisher_name,p.trusted publisher_trusted FROM marketplace_catalogs c LEFT JOIN marketplace_publishers p ON p.id=c.publisher_id ORDER BY c.name")]
        packages = [dict(r) for r in conn.execute("SELECT m.*,p.trusted publisher_trusted FROM marketplace_packages m LEFT JOIN marketplace_publishers p ON p.fingerprint=m.publisher_fingerprint WHERE m.available=1 ORDER BY m.name,m.version DESC")]
        installed = [dict(r) for r in conn.execute("SELECT * FROM installed_plugins ORDER BY name")]
        jobs = [dict(r) for r in conn.execute("SELECT j.*,u.username created_by_name FROM plugin_jobs j LEFT JOIN users u ON u.id=j.created_by ORDER BY j.id DESC LIMIT 100")]
    return render("marketplace.html", request, title="Marketplace", publishers=publishers, catalogs=catalogs, packages=packages, installed=installed, jobs=jobs, permissions=sorted(PERMISSIONS), message=message, error=error)


@app.post("/marketplace/publishers/add")
def publisher_add(request: Request, name: str = Form(...), fingerprint: str = Form(...), public_key: str = Form(""), trusted: int = Form(0)):
    require_admin(request)
    fp = re.sub(r"[^A-Fa-f0-9]", "", fingerprint).lower()
    if len(fp) != 64:
        raise HTTPException(400, "Herausgeber-Fingerprint muss SHA256 entsprechen")
    with db() as conn:
        conn.execute("INSERT INTO marketplace_publishers(name,fingerprint,public_key,trusted) VALUES(?,?,?,?)", (name.strip()[:120], fp, public_key.strip()[:10000], 1 if trusted else 0))
    audit("marketplace.publisher_added", None, fp)
    return RedirectResponse("/marketplace?message=Herausgeber+wurde+angelegt", 303)


@app.post("/marketplace/publishers/{publisher_id}/trust")
def publisher_trust(publisher_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        conn.execute("UPDATE marketplace_publishers SET trusted=CASE trusted WHEN 1 THEN 0 ELSE 1 END,updated_at=CURRENT_TIMESTAMP WHERE id=?", (publisher_id,))
    return RedirectResponse("/marketplace?message=Vertrauen+wurde+geändert", 303)


@app.post("/marketplace/packages/add")
def package_add(request: Request, plugin_id: str = Form(...), name: str = Form(...), version: str = Form(...), description: str = Form(""), package_url: str = Form(""), sha256: str = Form(...), publisher_fingerprint: str = Form(...), permissions: str = Form(""), dependencies: str = Form(""), signature: str = Form("")):
    require_admin(request)
    pid = plugin_id.strip().lower()
    clean_version = version.strip()
    digest = sha256.strip().lower()
    fp = re.sub(r"[^A-Fa-f0-9]", "", publisher_fingerprint).lower()
    if not PLUGIN_ID_RE.fullmatch(pid) or not VERSION_RE.fullmatch(clean_version) or not re.fullmatch(r"[a-f0-9]{64}", digest) or len(fp) != 64:
        raise HTTPException(400, "Ungültiges Plugin-Manifest")
    perms = _json_list(permissions, PERMISSIONS)
    deps = _json_list(dependencies)
    if any(not PLUGIN_ID_RE.fullmatch(dep) for dep in deps):
        raise HTTPException(400, "Ungültige Plugin-Abhängigkeit")
    manifest = {"id": pid, "name": name.strip()[:120], "version": clean_version, "permissions": perms, "dependencies": deps, "publisher": fp}
    with db() as conn:
        pub = conn.execute("SELECT trusted FROM marketplace_publishers WHERE fingerprint=?", (fp,)).fetchone()
        if not pub:
            raise HTTPException(400, "Herausgeber ist nicht registriert")
        conn.execute("INSERT INTO marketplace_packages(plugin_id,name,version,description,package_url,sha256,signature,publisher_fingerprint,permissions_json,dependencies_json,manifest_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (pid, name.strip()[:120], clean_version, description.strip()[:1000], package_url.strip()[:1000], digest, signature.strip()[:20000], fp, json.dumps(perms), json.dumps(deps), json.dumps(manifest)))
    audit("marketplace.package_added", None, f"{pid}:{clean_version}")
    return RedirectResponse("/marketplace?message=Plugin-Paket+wurde+registriert", 303)


@app.post("/marketplace/plugins/{plugin_id}/action")
def plugin_action(plugin_id: str, request: Request, action: str = Form(...), package_id: int = Form(0), package_file: str = Form("")):
    user = require_admin(request)
    if not PLUGIN_ID_RE.fullmatch(plugin_id) or action not in ACTIONS:
        raise HTTPException(400, "Ungültige Plugin-Aktion")
    if action in {"install", "update"} and (not package_id or not package_file):
        raise HTTPException(400, "Paket und Paketdatei sind für Installation oder Update erforderlich")
    package = None
    with db() as conn:
        if package_id:
            package = conn.execute("SELECT m.*,p.trusted publisher_trusted FROM marketplace_packages m LEFT JOIN marketplace_publishers p ON p.fingerprint=m.publisher_fingerprint WHERE m.id=? AND m.plugin_id=? AND m.available=1", (package_id, plugin_id)).fetchone()
            if not package or not package["publisher_trusted"]:
                raise HTTPException(400, "Plugin-Herausgeber ist nicht vertrauenswürdig")
            deps = json.loads(package["dependencies_json"] or "[]")
            for dependency in deps:
                row = conn.execute("SELECT enabled FROM installed_plugins WHERE plugin_id=?", (dependency,)).fetchone()
                if not row or not row["enabled"]:
                    raise HTTPException(409, f"Abhängigkeit fehlt oder ist deaktiviert: {dependency}")
        cursor = conn.execute("INSERT INTO plugin_jobs(plugin_id,action,created_by) VALUES(?,?,?)", (plugin_id, action, user["id"]))
        job_id = cursor.lastrowid
    try:
        result = _run_helper(action, plugin_id, package_file, package["sha256"] if package else "")
        if result["state"] != "succeeded":
            raise RuntimeError(result["error"] or "Plugin-Aktion fehlgeschlagen")
        with db() as conn:
            if action in {"install", "update"} and package:
                conn.execute("INSERT INTO installed_plugins(plugin_id,name,version,enabled,publisher_fingerprint,permissions_json,dependencies_json,package_sha256) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(plugin_id) DO UPDATE SET name=excluded.name,version=excluded.version,publisher_fingerprint=excluded.publisher_fingerprint,permissions_json=excluded.permissions_json,dependencies_json=excluded.dependencies_json,package_sha256=excluded.package_sha256,updated_at=CURRENT_TIMESTAMP,last_error=''", (plugin_id, package["name"], package["version"], 0, package["publisher_fingerprint"], package["permissions_json"], package["dependencies_json"], package["sha256"]))
            elif action in {"enable", "disable"}:
                conn.execute("UPDATE installed_plugins SET enabled=?,updated_at=CURRENT_TIMESTAMP,last_error='' WHERE plugin_id=?", (1 if action == "enable" else 0, plugin_id))
            elif action == "remove":
                conn.execute("DELETE FROM installed_plugins WHERE plugin_id=?", (plugin_id,))
            conn.execute("UPDATE plugin_jobs SET state='succeeded',output=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (result["output"], job_id))
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE plugin_jobs SET state='failed',error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:100000], job_id))
            conn.execute("UPDATE installed_plugins SET last_error=? WHERE plugin_id=?", (str(exc)[:100000], plugin_id))
        return RedirectResponse("/marketplace?error=" + urllib.parse.quote(str(exc)[:700]), 303)
    audit("marketplace.plugin_action", None, f"{plugin_id}:{action}")
    return RedirectResponse("/marketplace?message=Plugin-Aktion+abgeschlossen", 303)


@app.get("/api/v1/marketplace")
def marketplace_api(request: Request):
    require_user(request)
    with db() as conn:
        publishers = [dict(r) for r in conn.execute("SELECT id,name,fingerprint,trusted,updated_at FROM marketplace_publishers ORDER BY name")]
        packages = [dict(r) for r in conn.execute("SELECT id,plugin_id,name,version,sha256,publisher_fingerprint,permissions_json,dependencies_json,available FROM marketplace_packages ORDER BY name,version DESC")]
        installed = [dict(r) for r in conn.execute("SELECT * FROM installed_plugins ORDER BY name")]
        jobs = [dict(r) for r in conn.execute("SELECT id,plugin_id,action,state,error,created_at,finished_at FROM plugin_jobs ORDER BY id DESC LIMIT 100")]
    return {"version": VERSION, "publishers": publishers, "packages": packages, "installed": installed, "jobs": jobs}
