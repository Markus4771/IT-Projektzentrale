from __future__ import annotations

"""Version 2.0.0: vollständiges Installationszentrum."""

import json
import re
import sqlite3
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user, validate_http_url
from app.v190 import app

VERSION = "2.0.0"
base.VERSION = VERSION
app.version = VERSION

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]{1,119}$")
ALLOWED_PROVIDERS = {"github", "gitea"}
ALLOWED_JOB_TYPES = {"refresh", "install", "update", "remove"}


def init_install_center_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS installation_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            job_type TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'queued',
            package_file TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            output TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS installation_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_installation_jobs_created ON installation_jobs(id DESC);
        CREATE INDEX IF NOT EXISTS idx_installation_jobs_state ON installation_jobs(state,id DESC);
        """)


@app.on_event("startup")
def initialize_v200() -> None:
    init_install_center_db()


def _installed_version(package_name: str) -> str:
    if not package_name or not PACKAGE_RE.fullmatch(package_name):
        return ""
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Version}", package_name],
        capture_output=True, text=True, timeout=15, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _installation_summary() -> dict[str, Any]:
    with db() as conn:
        projects = [dict(row) for row in conn.execute(
            """SELECT p.*, ps.provider AS source_provider, ps.repository AS source_repository,
                      ps.enabled AS source_enabled, ps.last_error AS source_error
               FROM projects p LEFT JOIN package_sources ps ON ps.project_id=p.id
               WHERE p.deleted_at IS NULL ORDER BY p.category,p.name"""
        )]
        jobs = [dict(row) for row in conn.execute(
            """SELECT j.*,p.name AS project_name,u.username AS created_by_name
               FROM installation_jobs j LEFT JOIN projects p ON p.id=j.project_id
               LEFT JOIN users u ON u.id=j.created_by ORDER BY j.id DESC LIMIT 100"""
        )]
        counts = dict(conn.execute(
            """SELECT
               SUM(CASE WHEN state='queued' THEN 1 ELSE 0 END) queued,
               SUM(CASE WHEN state='running' THEN 1 ELSE 0 END) running,
               SUM(CASE WHEN state='failed' THEN 1 ELSE 0 END) failed,
               SUM(CASE WHEN state='succeeded' THEN 1 ELSE 0 END) succeeded
               FROM installation_jobs"""
        ).fetchone())
    installed = 0
    updates = 0
    for project in projects:
        version = _installed_version(project.get("package_name") or "")
        project["detected_installed_version"] = version
        if version:
            installed += 1
        latest = str(project.get("latest_version") or "")
        if version and latest and latest != version:
            project["update_available"] = True
            updates += 1
        else:
            project["update_available"] = False
    return {"projects": projects, "jobs": jobs, "counts": counts, "installed": installed, "updates": updates}


@app.get("/installation/catalog", response_class=HTMLResponse)
def installation_catalog(request: Request, message: str = "", error: str = ""):
    require_user(request)
    summary = _installation_summary()
    return render("installation_catalog.html", request, title="Projekt-Katalog", message=message,
                  error=error, **summary)


@app.get("/installation/sources", response_class=HTMLResponse)
def installation_sources(request: Request, message: str = "", error: str = ""):
    require_admin(request)
    with db() as conn:
        rows = conn.execute(
            """SELECT p.id,p.name,p.package_name,ps.provider,ps.base_url,ps.repository,
                      ps.asset_pattern,ps.enabled,ps.last_error,ps.updated_at
               FROM projects p LEFT JOIN package_sources ps ON ps.project_id=p.id
               WHERE p.deleted_at IS NULL ORDER BY p.name"""
        ).fetchall()
    return render("installation_sources.html", request, title="Paketquellen", sources=[dict(r) for r in rows],
                  message=message, error=error)


@app.post("/installation/sources/{project_id}")
def save_installation_source(project_id: int, request: Request, provider: str = Form(...),
                             base_url: str = Form(""), repository: str = Form(...),
                             asset_pattern: str = Form("*.deb"), enabled: bool = Form(False)):
    user = require_admin(request)
    provider = provider.strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        return RedirectResponse("/installation/sources?error=Ungültiger+Anbieter", 303)
    repository = repository.strip()
    if not REPOSITORY_RE.fullmatch(repository):
        return RedirectResponse("/installation/sources?error=Repository+muss+Eigentümer/Name+enthalten", 303)
    default_url = "https://github.com" if provider == "github" else ""
    try:
        clean_url = validate_http_url(base_url.strip() or default_url, "Quellserver")
    except ValueError as exc:
        return RedirectResponse("/installation/sources?error=" + urllib.parse.quote(str(exc)), 303)
    pattern = asset_pattern.strip()[:200] or "*.deb"
    with db() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone():
            raise HTTPException(404, "Projekt nicht gefunden")
        conn.execute(
            """INSERT INTO package_sources(project_id,provider,base_url,repository,token,asset_pattern,enabled)
               VALUES(?,?,?,?, '',?,?) ON CONFLICT(project_id) DO UPDATE SET
               provider=excluded.provider,base_url=excluded.base_url,repository=excluded.repository,
               asset_pattern=excluded.asset_pattern,enabled=excluded.enabled,last_error='',updated_at=CURRENT_TIMESTAMP""",
            (project_id, provider, clean_url, repository, pattern, int(enabled)),
        )
    audit("installation.source_saved", project_id, f"{provider}:{repository}")
    return RedirectResponse("/installation/sources?message=Paketquelle+wurde+gespeichert", 303)


@app.get("/installation/updates", response_class=HTMLResponse)
def installation_updates(request: Request):
    require_user(request)
    summary = _installation_summary()
    return render("installation_updates.html", request, title="Projekt-Updates", **summary)


@app.get("/installation/queue", response_class=HTMLResponse)
def installation_queue(request: Request):
    require_user(request)
    summary = _installation_summary()
    return render("installation_queue.html", request, title="Installationswarteschlange", **summary)


@app.post("/installation/jobs/{project_id}/enqueue")
def enqueue_installation_job(project_id: int, request: Request, job_type: str = Form(...)):
    user = require_admin(request)
    if job_type not in ALLOWED_JOB_TYPES:
        raise HTTPException(400, "Unbekannter Auftragstyp")
    with db() as conn:
        project = conn.execute("SELECT id,name FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Projekt nicht gefunden")
        duplicate = conn.execute(
            "SELECT 1 FROM installation_jobs WHERE project_id=? AND job_type=? AND state IN ('queued','running')",
            (project_id, job_type),
        ).fetchone()
        if duplicate:
            return RedirectResponse("/installation/queue?error=Auftrag+ist+bereits+vorgemerkt", 303)
        conn.execute(
            "INSERT INTO installation_jobs(project_id,job_type,created_by) VALUES(?,?,?)",
            (project_id, job_type, user["id"]),
        )
    audit("installation.job_enqueued", project_id, job_type)
    return RedirectResponse("/installation/queue?message=Auftrag+wurde+vorgemerkt", 303)


@app.post("/installation/jobs/{job_id}/cancel")
def cancel_installation_job(job_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        cursor = conn.execute(
            "UPDATE installation_jobs SET state='cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=? AND state='queued'",
            (job_id,),
        )
    if cursor.rowcount == 0:
        return RedirectResponse("/installation/queue?error=Auftrag+kann+nicht+mehr+abgebrochen+werden", 303)
    audit("installation.job_cancelled", None, f"#{job_id}")
    return RedirectResponse("/installation/queue?message=Auftrag+wurde+abgebrochen", 303)


@app.get("/api/v1/installation")
def installation_api(request: Request):
    require_user(request)
    summary = _installation_summary()
    return {
        "version": VERSION,
        "installed": summary["installed"],
        "updates": summary["updates"],
        "queue": summary["counts"],
        "projects": [
            {"id": p["id"], "name": p["name"], "category": p.get("category"),
             "package": p.get("package_name"), "installed_version": p.get("detected_installed_version"),
             "latest_version": p.get("latest_version"), "update_available": p.get("update_available"),
             "provider": p.get("source_provider"), "repository": p.get("source_repository")}
            for p in summary["projects"]
        ],
    }
