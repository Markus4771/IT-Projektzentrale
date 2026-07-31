from __future__ import annotations

"""Version 2.1.0: produktive Installations-Engine und Live-Status."""

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v200 import app, init_install_center_db

VERSION = "2.1.0"
base.VERSION = VERSION
app.version = VERSION

TERMINAL_STATES = {"succeeded", "failed", "cancelled", "rolled_back"}


def init_install_engine_db() -> None:
    init_install_center_db()
    with db() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(installation_jobs)")}
        additions = {
            "progress": "INTEGER NOT NULL DEFAULT 0",
            "phase": "TEXT NOT NULL DEFAULT 'queued'",
            "backup_path": "TEXT NOT NULL DEFAULT ''",
            "previous_version": "TEXT NOT NULL DEFAULT ''",
            "target_version": "TEXT NOT NULL DEFAULT ''",
            "worker_id": "TEXT NOT NULL DEFAULT ''",
            "heartbeat_at": "TEXT",
            "rollback_state": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE installation_jobs ADD COLUMN {name} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_installation_worker ON installation_jobs(state,id)")


@app.on_event("startup")
def initialize_v210() -> None:
    init_install_engine_db()


def _job(job_id: int):
    with db() as conn:
        row = conn.execute(
            """SELECT j.*,p.name AS project_name,p.package_name,p.service_name,p.health_url,
                      p.latest_version,u.username AS created_by_name
               FROM installation_jobs j LEFT JOIN projects p ON p.id=j.project_id
               LEFT JOIN users u ON u.id=j.created_by WHERE j.id=?""",
            (job_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Installationsauftrag nicht gefunden")
    return dict(row)


@app.get("/installation/jobs/{job_id}", response_class=HTMLResponse)
def installation_job_detail(job_id: int, request: Request):
    require_user(request)
    return render("installation_job.html", request, title=f"Installationsauftrag #{job_id}", job=_job(job_id))


@app.post("/installation/jobs/{job_id}/retry")
def retry_installation_job(job_id: int, request: Request):
    user = require_admin(request)
    original = _job(job_id)
    if original["state"] not in TERMINAL_STATES:
        raise HTTPException(409, "Nur abgeschlossene Aufträge können erneut gestartet werden")
    with db() as conn:
        duplicate = conn.execute(
            "SELECT 1 FROM installation_jobs WHERE project_id=? AND state IN ('queued','running')",
            (original["project_id"],),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "Für dieses Projekt läuft bereits ein Auftrag")
        cursor = conn.execute(
            """INSERT INTO installation_jobs(project_id,job_type,package_file,source,created_by,phase)
               VALUES(?,?,?,?,?,'queued')""",
            (original["project_id"], original["job_type"], original["package_file"], original["source"], user["id"]),
        )
    audit("installation.job_retried", original["project_id"], f"#{job_id} -> #{cursor.lastrowid}")
    return RedirectResponse(f"/installation/jobs/{cursor.lastrowid}", 303)


@app.post("/installation/jobs/{job_id}/rollback")
def request_installation_rollback(job_id: int, request: Request):
    require_admin(request)
    job = _job(job_id)
    if job["state"] not in {"succeeded", "failed"} or not job.get("backup_path"):
        raise HTTPException(409, "Für diesen Auftrag ist kein Rollback verfügbar")
    with db() as conn:
        duplicate = conn.execute(
            "SELECT 1 FROM installation_jobs WHERE project_id=? AND state IN ('queued','running')",
            (job["project_id"],),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "Für dieses Projekt läuft bereits ein Auftrag")
        cursor = conn.execute(
            """INSERT INTO installation_jobs(project_id,job_type,package_file,source,backup_path,
                                               previous_version,target_version,created_by,phase)
               VALUES(?,'rollback',?,?,?,?,?,?,'queued')""",
            (job["project_id"], job["package_file"], f"rollback:{job_id}", job["backup_path"],
             job["previous_version"], job["target_version"], request.session["user_id"]),
        )
    audit("installation.rollback_queued", job["project_id"], f"#{cursor.lastrowid}")
    return RedirectResponse(f"/installation/jobs/{cursor.lastrowid}", 303)


@app.get("/api/v1/install/jobs")
def install_jobs_api(request: Request):
    require_user(request)
    with db() as conn:
        rows = conn.execute(
            """SELECT j.id,j.project_id,p.name AS project,j.job_type,j.state,j.phase,j.progress,
                      j.created_at,j.started_at,j.finished_at,j.error
               FROM installation_jobs j LEFT JOIN projects p ON p.id=j.project_id
               ORDER BY j.id DESC LIMIT 200"""
        ).fetchall()
    return {"version": VERSION, "jobs": [dict(row) for row in rows]}


@app.get("/api/v1/install/jobs/{job_id}")
def install_job_api(job_id: int, request: Request):
    require_user(request)
    return _job(job_id)


@app.post("/api/v1/install/jobs/{job_id}/cancel")
def cancel_install_job_api(job_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        cursor = conn.execute(
            """UPDATE installation_jobs SET state='cancelled',phase='cancelled',finished_at=CURRENT_TIMESTAMP
               WHERE id=? AND state='queued'""",
            (job_id,),
        )
    if cursor.rowcount != 1:
        raise HTTPException(409, "Auftrag kann nicht mehr abgebrochen werden")
    return {"ok": True, "job_id": job_id}
