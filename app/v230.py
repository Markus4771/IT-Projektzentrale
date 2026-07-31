from __future__ import annotations

"""Version 2.3.0: lokale und entfernte Docker-Compose-Verwaltung."""

import json
import re
import subprocess
import urllib.parse
from pathlib import Path

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v220_runtime import app
from app.v220 import _agent_request

VERSION = "2.3.0"
base.VERSION = VERSION
app.version = VERSION
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
ACTIONS = {"status", "up", "down", "restart", "pull", "update", "logs", "backup", "rollback"}
HELPER = "/usr/lib/it-projektzentrale/itpz-compose-helper"


def init_compose_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS compose_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            server_id INTEGER,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'unknown',
            last_output TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            last_backup TEXT NOT NULL DEFAULT '',
            last_checked_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(server_id,slug),
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS compose_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compose_project_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'running',
            output TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            backup_file TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            FOREIGN KEY(compose_project_id) REFERENCES compose_projects(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_compose_jobs_project ON compose_jobs(compose_project_id,id DESC);
        """)


@app.on_event("startup")
def initialize_v230() -> None:
    init_compose_db()


def _local_action(slug: str, action: str, backup_file: str = "") -> dict:
    args = ["/usr/bin/sudo", HELPER, action, slug]
    if action == "rollback":
        args.append(Path(backup_file).name)
    result = subprocess.run(args, capture_output=True, text=True, timeout=1800, check=False)
    output = result.stdout[-200000:]
    error = result.stderr[-200000:]
    data = {"state": "succeeded" if result.returncode == 0 else "failed", "output": output, "error": error}
    if action == "backup" and result.returncode == 0:
        try:
            parsed = json.loads(output)
            data["backup_file"] = Path(str(parsed.get("backup") or "")).name
        except (json.JSONDecodeError, TypeError):
            pass
    return data


def _compose_action(project, action: str, backup_file: str = "") -> dict:
    if project["server_id"] is None:
        return _local_action(project["slug"], action, backup_file)
    with db() as conn:
        server = conn.execute("SELECT * FROM servers WHERE id=? AND connection_type='agent' AND enabled=1", (project["server_id"],)).fetchone()
    if not server:
        raise RuntimeError("Remote-Agent nicht verfügbar")
    payload = {"slug": project["slug"]}
    if action == "rollback":
        payload["backup_file"] = Path(backup_file).name
    return _agent_request(server, f"/v1/jobs", "POST", {"action": f"compose-{action}", "payload": payload})


def _projects() -> list[dict]:
    with db() as conn:
        rows = conn.execute("""SELECT c.*,s.name AS server_name,s.last_status AS server_status
            FROM compose_projects c LEFT JOIN servers s ON s.id=c.server_id
            ORDER BY COALESCE(s.name,'Lokal'),c.name""").fetchall()
    return [dict(row) for row in rows]


@app.get("/compose", response_class=HTMLResponse)
def compose_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        servers = [dict(r) for r in conn.execute("SELECT id,name,hostname,last_status FROM servers WHERE connection_type='agent' AND enabled=1 ORDER BY name")]
        jobs = [dict(r) for r in conn.execute("""SELECT j.*,c.name project_name,c.slug,s.name server_name,u.username created_by_name
            FROM compose_jobs j JOIN compose_projects c ON c.id=j.compose_project_id
            LEFT JOIN servers s ON s.id=c.server_id LEFT JOIN users u ON u.id=j.created_by
            ORDER BY j.id DESC LIMIT 100""")]
    return render("compose.html", request, title="Docker Compose", projects=_projects(), servers=servers, jobs=jobs, message=message, error=error)


@app.post("/compose/add")
def compose_add(request: Request, name: str = Form(...), slug: str = Form(...), server_id: str = Form(""), description: str = Form("")):
    require_admin(request)
    clean_slug = slug.strip().lower()
    if not SLUG_RE.fullmatch(clean_slug):
        return RedirectResponse("/compose?error=Ungültige+Projekt-ID", 303)
    target_server = int(server_id) if server_id.strip().isdigit() else None
    try:
        with db() as conn:
            if target_server and not conn.execute("SELECT 1 FROM servers WHERE id=? AND connection_type='agent'", (target_server,)).fetchone():
                raise ValueError("Remote-Server nicht gefunden")
            conn.execute("INSERT INTO compose_projects(name,slug,server_id,description) VALUES(?,?,?,?)",
                         (name.strip()[:120], clean_slug, target_server, description.strip()[:1000]))
    except Exception as exc:
        return RedirectResponse("/compose?error=" + urllib.parse.quote(str(exc)[:500]), 303)
    audit("compose.added", None, clean_slug)
    return RedirectResponse("/compose?message=Compose-Projekt+wurde+angelegt", 303)


@app.post("/compose/{project_id}/action")
def compose_action(project_id: int, request: Request, action: str = Form(...), backup_file: str = Form("")):
    user = require_admin(request)
    if action not in ACTIONS:
        raise HTTPException(400, "Nicht erlaubte Compose-Aktion")
    with db() as conn:
        project = conn.execute("SELECT * FROM compose_projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Compose-Projekt nicht gefunden")
        if action == "rollback" and (not backup_file or "/" in backup_file or "\\" in backup_file):
            raise HTTPException(400, "Ungültige Backup-Datei")
        cursor = conn.execute("INSERT INTO compose_jobs(compose_project_id,action,created_by) VALUES(?,?,?)", (project_id, action, user["id"]))
        job_id = cursor.lastrowid
    try:
        result = _compose_action(project, action, backup_file)
        state = str(result.get("state") or "failed")
        output = str(result.get("output") or "")[-200000:]
        error = str(result.get("error") or "")[-200000:]
        backup = Path(str(result.get("backup_file") or "")).name
        status = "running" if state == "succeeded" and action in {"up", "restart", "update", "rollback"} else "stopped" if state == "succeeded" and action == "down" else project["status"]
        with db() as conn:
            conn.execute("UPDATE compose_jobs SET state=?,output=?,error=?,backup_file=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (state, output, error, backup, job_id))
            conn.execute("UPDATE compose_projects SET status=?,last_output=?,last_error=?,last_backup=CASE WHEN ?='' THEN last_backup ELSE ? END,last_checked_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (status, output, error, backup, backup, project_id))
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE compose_jobs SET state='failed',error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:200000], job_id))
            conn.execute("UPDATE compose_projects SET last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:200000], project_id))
        return RedirectResponse("/compose?error=" + urllib.parse.quote(str(exc)[:700]), 303)
    audit("compose.action", project_id, action)
    return RedirectResponse("/compose?message=Compose-Aktion+abgeschlossen", 303)


@app.post("/compose/{project_id}/delete")
def compose_delete(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        conn.execute("DELETE FROM compose_projects WHERE id=?", (project_id,))
    audit("compose.deleted", project_id, "Registry-Eintrag entfernt")
    return RedirectResponse("/compose?message=Compose-Projekt+wurde+aus+der+Verwaltung+entfernt", 303)


@app.get("/api/v1/compose")
def compose_api(request: Request):
    require_user(request)
    with db() as conn:
        jobs = [dict(r) for r in conn.execute("SELECT id,compose_project_id,action,state,backup_file,created_at,finished_at,error FROM compose_jobs ORDER BY id DESC LIMIT 100")]
    return {"version": VERSION, "projects": _projects(), "jobs": jobs}
