from __future__ import annotations

"""Version 1.4.0: Software-Center mit Release-Abruf und Installationsjobs."""

import json
import sqlite3
import urllib.parse
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import (
    PACKAGE_DIR,
    audit,
    db,
    download_asset,
    installed_version,
    latest_deb_asset,
    package_metadata,
    render,
    require_admin,
    require_user,
    run_helper,
    version_is_newer,
)
from app.v130 import app, init_platform_db

VERSION = "1.4.0"
base.VERSION = VERSION
app.version = VERSION


def _set_job(job_id: int, state: str, progress: int, *, result: dict | None = None, error: str = "") -> None:
    with db() as conn:
        conn.execute(
            """UPDATE jobs SET state=?,progress=?,result_json=?,error=?,
               started_at=CASE WHEN ?='running' AND started_at IS NULL THEN CURRENT_TIMESTAMP ELSE started_at END,
               finished_at=CASE WHEN ? IN ('succeeded','failed','cancelled') THEN CURRENT_TIMESTAMP ELSE finished_at END
               WHERE id=?""",
            (state, progress, json.dumps(result or {}, ensure_ascii=False), error[:2000], state, state, job_id),
        )


def _queue(job_type: str, project_id: int, user_id: int, payload: dict | None = None) -> int:
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO jobs(job_type,project_id,payload_json,created_by) VALUES(?,?,?,?)",
            (job_type, project_id, json.dumps(payload or {}, ensure_ascii=False), user_id),
        )
        return int(cursor.lastrowid)


def _project_and_source(project_id: int) -> tuple[sqlite3.Row, sqlite3.Row | None]:
    with db() as conn:
        project = conn.execute(
            "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)
        ).fetchone()
        source = conn.execute(
            "SELECT * FROM package_sources WHERE project_id=? AND enabled=1", (project_id,)
        ).fetchone()
    if not project:
        raise HTTPException(404, "Projekt nicht gefunden")
    return project, source


@app.on_event("startup")
def initialize_v140() -> None:
    init_platform_db()


@app.get("/software-center", response_class=HTMLResponse)
def software_center(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        rows = conn.execute(
            """SELECT p.*,
               s.provider source_provider,s.base_url source_base_url,s.repository source_repository,
               s.asset_pattern source_pattern,s.last_checked_at source_last_checked,s.last_error source_error,
               (SELECT version FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_version,
               (SELECT filename FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_file,
               (SELECT source FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_source
               FROM projects p LEFT JOIN package_sources s ON s.project_id=p.id
               WHERE p.deleted_at IS NULL AND p.archived=0
               ORDER BY p.category,p.name"""
        ).fetchall()
        jobs = conn.execute(
            """SELECT j.*,p.name project_name FROM jobs j
               LEFT JOIN projects p ON p.id=j.project_id ORDER BY j.id DESC LIMIT 20"""
        ).fetchall()
    projects = []
    for row in rows:
        item = dict(row)
        current = installed_version(row["package_name"])
        item["installed_version"] = current
        item["update_available"] = version_is_newer(row["latest_version"], current)
        if current:
            item["software_status"] = "update" if item["update_available"] else "installed"
        elif row["latest_file"]:
            item["software_status"] = "ready"
        elif row["source_provider"]:
            item["software_status"] = "source"
        else:
            item["software_status"] = "unconfigured"
        projects.append(item)
    return render(
        "software_center.html",
        request,
        title="Software-Center",
        projects=projects,
        jobs=[dict(row) for row in jobs],
        message=message,
        error=error,
        software_center_version=VERSION,
    )


@app.post("/software-center/{project_id}/refresh")
def software_center_refresh(project_id: int, request: Request):
    user = require_admin(request)
    project, source = _project_and_source(project_id)
    if not source:
        return RedirectResponse("/software-center?error=Keine+aktive+GitHub-+oder+Gitea-Quelle+eingerichtet", 303)
    job_id = _queue("software.release.refresh", project_id, user["id"], {"provider": source["provider"]})
    _set_job(job_id, "running", 10)
    temporary: Path | None = None
    try:
        filename, release_version, url = latest_deb_asset(source)
        safe_name = Path(filename).name
        temporary = PACKAGE_DIR / f".software-center-{job_id}.deb"
        _set_job(job_id, "running", 35, result={"release_version": release_version})
        digest = download_asset(url, temporary, source["token"], source["provider"])
        metadata = package_metadata(temporary)
        if project["package_name"] and project["package_name"] != metadata["package"]:
            raise RuntimeError("Der Paketname des Releases stimmt nicht mit dem Projekt überein")
        target = PACKAGE_DIR / safe_name
        temporary.replace(target)
        temporary = None
        with db() as conn:
            conn.execute(
                """INSERT INTO packages(project_id,filename,version,sha256,source)
                   SELECT ?,?,?,?,? WHERE NOT EXISTS(
                     SELECT 1 FROM packages WHERE project_id=? AND filename=? AND sha256=?
                   )""",
                (project_id, safe_name, metadata["version"], digest, source["provider"], project_id, safe_name, digest),
            )
            conn.execute(
                "UPDATE package_sources SET last_checked_at=CURRENT_TIMESTAMP,last_error='' WHERE project_id=?",
                (project_id,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO project_versions(project_id,version,channel,source,released_at) VALUES(?,?,'stable',?,CURRENT_TIMESTAMP)",
                (project_id, metadata["version"], source["provider"]),
            )
        _set_job(job_id, "succeeded", 100, result={"filename": safe_name, "version": metadata["version"], "sha256": digest})
        audit("software.release.refreshed", project_id, f"Job #{job_id}: {metadata['version']}")
        return RedirectResponse("/software-center?message=Neuestes+Release+wurde+abgerufen", 303)
    except Exception as exc:
        if temporary:
            temporary.unlink(missing_ok=True)
        with db() as conn:
            conn.execute(
                "UPDATE package_sources SET last_checked_at=CURRENT_TIMESTAMP,last_error=? WHERE project_id=?",
                (str(exc)[:900], project_id),
            )
        _set_job(job_id, "failed", 100, error=str(exc))
        audit("software.release.failed", project_id, f"Job #{job_id}: {str(exc)[:700]}")
        return RedirectResponse(f"/software-center?error={urllib.parse.quote(str(exc)[:900])}", 303)


@app.post("/software-center/{project_id}/install")
def software_center_install(project_id: int, request: Request):
    user = require_admin(request)
    project, _ = _project_and_source(project_id)
    with db() as conn:
        package = conn.execute(
            "SELECT * FROM packages WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)
        ).fetchone()
    if not package:
        return RedirectResponse("/software-center?error=Noch+kein+DEB-Paket+abgerufen", 303)
    job_id = _queue("software.package.install", project_id, user["id"], {"filename": package["filename"]})
    _set_job(job_id, "running", 15)
    path = PACKAGE_DIR / Path(package["filename"]).name
    try:
        metadata = package_metadata(path)
        if project["package_name"] and project["package_name"] != metadata["package"]:
            raise RuntimeError("Der Paketname stimmt nicht mit dem Projekt überein")
        _set_job(job_id, "running", 45, result={"package": metadata["package"], "version": metadata["version"]})
        result = run_helper("install", str(path))
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Installation fehlgeschlagen")[-1800:])
        installed = installed_version(metadata["package"])
        with db() as conn:
            conn.execute(
                "UPDATE projects SET install_status='installed',version=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (installed or metadata["version"], project_id),
            )
        _set_job(job_id, "succeeded", 100, result={"package": metadata["package"], "installed_version": installed or metadata["version"]})
        audit("software.package.installed", project_id, f"Job #{job_id}: {installed or metadata['version']}")
        return RedirectResponse("/software-center?message=Installation+oder+Update+erfolgreich+abgeschlossen", 303)
    except Exception as exc:
        _set_job(job_id, "failed", 100, error=str(exc))
        audit("software.package.failed", project_id, f"Job #{job_id}: {str(exc)[:700]}")
        return RedirectResponse(f"/software-center?error={urllib.parse.quote(str(exc)[:900])}", 303)


@app.get("/api/v1/software-center")
def software_center_api(request: Request):
    require_user(request)
    with db() as conn:
        rows = conn.execute(
            """SELECT p.id,p.name,p.slug,p.category,p.package_name,p.install_status,
               s.provider,s.repository,s.last_checked_at,s.last_error,
               (SELECT version FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_version
               FROM projects p LEFT JOIN package_sources s ON s.project_id=p.id
               WHERE p.deleted_at IS NULL AND p.archived=0 ORDER BY p.name"""
        ).fetchall()
    return [{**dict(row), "installed_version": installed_version(row["package_name"])} for row in rows]
