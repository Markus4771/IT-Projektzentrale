from __future__ import annotations

"""Version 2.2.0: sichere Remote-Agent-Verwaltung."""

import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user, validate_http_url
from app.v210_runtime import app

VERSION = "2.2.0"
base.VERSION = VERSION
app.version = VERSION
ALLOWED_REMOTE_ACTIONS = {"status", "apt-update", "apt-upgrade", "backup", "install"}


def init_remote_agent_db() -> None:
    with db() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(servers)")}
        for statement, column in (
            ("ALTER TABLE servers ADD COLUMN agent_token_hash TEXT NOT NULL DEFAULT ''", "agent_token_hash"),
            ("ALTER TABLE servers ADD COLUMN agent_version TEXT NOT NULL DEFAULT ''", "agent_version"),
            ("ALTER TABLE servers ADD COLUMN agent_fingerprint TEXT NOT NULL DEFAULT ''", "agent_fingerprint"),
            ("ALTER TABLE servers ADD COLUMN registered_at TEXT", "registered_at"),
        ):
            if column not in columns:
                conn.execute(statement)
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS remote_agent_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            state TEXT NOT NULL DEFAULT 'queued',
            remote_job_id TEXT NOT NULL DEFAULT '',
            output TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_remote_agent_jobs_server ON remote_agent_jobs(server_id,id DESC);
        """)


@app.on_event("startup")
def initialize_v220() -> None:
    init_remote_agent_db()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _agent_request(server: Any, path: str, method: str = "GET", payload: dict | None = None) -> dict:
    base_url = validate_http_url(server["agent_url"], "Agent-URL").rstrip("/")
    token = server["agent_token_hash"] or ""
    if not token:
        raise RuntimeError("Agent ist noch nicht registriert")
    data = json.dumps(payload or {}).encode("utf-8") if method != "GET" else None
    request = urllib.request.Request(
        base_url + path,
        data=data,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", "Authorization": f"Bearer {token}", "User-Agent": "ITPZ/2.2"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Agent meldet HTTP {exc.code}") from exc
    if len(raw) > 2 * 1024 * 1024:
        raise RuntimeError("Agent-Antwort ist zu groß")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError("Ungültige Agent-Antwort")
    return result


@app.post("/servers/{server_id}/registration-token")
def create_registration_token(server_id: int, request: Request):
    require_admin(request)
    token = secrets.token_urlsafe(32)
    digest = _token_hash(token)
    with db() as conn:
        row = conn.execute("SELECT id FROM servers WHERE id=? AND connection_type='agent'", (server_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Remote-Server nicht gefunden")
        conn.execute("UPDATE servers SET agent_token_hash=?,registered_at=NULL WHERE id=?", (digest, server_id))
    audit("agent.registration_token", server_id, "Token neu erzeugt")
    return render("agent_token.html", request, title="Agent registrieren", server_id=server_id, token=token, token_hash=digest)


@app.post("/servers/{server_id}/agent-test")
def test_remote_agent(server_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        server = conn.execute("SELECT * FROM servers WHERE id=?", (server_id,)).fetchone()
    if not server:
        raise HTTPException(404, "Server nicht gefunden")
    try:
        data = _agent_request(server, "/v1/status")
        with db() as conn:
            conn.execute("UPDATE servers SET last_status='online',last_error='',last_seen_at=CURRENT_TIMESTAMP,agent_version=?,agent_fingerprint=?,registered_at=COALESCE(registered_at,CURRENT_TIMESTAMP) WHERE id=?",
                         (str(data.get("agent_version") or "")[:40], str(data.get("fingerprint") or "")[:128], server_id))
        return RedirectResponse("/servers?message=Agent-Verbindung+erfolgreich", 303)
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE servers SET last_status='offline',last_error=? WHERE id=?", (str(exc)[:900], server_id))
        return RedirectResponse("/servers?error=" + urllib.parse.quote(str(exc)), 303)


@app.post("/servers/{server_id}/remote-action")
def enqueue_remote_action(server_id: int, request: Request, action: str = Form(...), package_file: str = Form("")):
    user = require_admin(request)
    if action not in ALLOWED_REMOTE_ACTIONS - {"status"}:
        raise HTTPException(400, "Nicht erlaubte Remote-Aktion")
    payload: dict[str, Any] = {}
    if action == "install":
        name = package_file.strip()
        if not name.endswith(".deb") or "/" in name or "\\" in name:
            raise HTTPException(400, "Ungültiger Paketname")
        payload["package_file"] = name
    with db() as conn:
        server = conn.execute("SELECT * FROM servers WHERE id=? AND connection_type='agent' AND enabled=1", (server_id,)).fetchone()
        if not server:
            raise HTTPException(404, "Remote-Server nicht gefunden")
        cursor = conn.execute("INSERT INTO remote_agent_jobs(server_id,action,payload_json,state,created_by,started_at) VALUES(?,?,?,'running',?,CURRENT_TIMESTAMP)",
                              (server_id, action, json.dumps(payload), user["id"]))
        job_id = cursor.lastrowid
    try:
        result = _agent_request(server, "/v1/jobs", "POST", {"action": action, "payload": payload})
        with db() as conn:
            conn.execute("UPDATE remote_agent_jobs SET state=?,remote_job_id=?,output=?,finished_at=CASE WHEN ? IN ('succeeded','failed') THEN CURRENT_TIMESTAMP END WHERE id=?",
                         (str(result.get("state") or "queued"), str(result.get("job_id") or ""), json.dumps(result, ensure_ascii=False)[:100000], str(result.get("state") or ""), job_id))
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE remote_agent_jobs SET state='failed',error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:5000], job_id))
        return RedirectResponse("/servers?error=" + urllib.parse.quote(str(exc)), 303)
    audit("agent.remote_action", server_id, action)
    return RedirectResponse("/servers?message=Remote-Auftrag+wurde+übermittelt", 303)


@app.get("/remote-jobs", response_class=HTMLResponse)
def remote_jobs_page(request: Request):
    require_user(request)
    with db() as conn:
        jobs = [dict(row) for row in conn.execute("SELECT j.*,s.name server_name,u.username created_by_name FROM remote_agent_jobs j JOIN servers s ON s.id=j.server_id LEFT JOIN users u ON u.id=j.created_by ORDER BY j.id DESC LIMIT 200")]
    return render("remote_jobs.html", request, title="Remote-Aufträge", jobs=jobs)


@app.get("/api/v1/remote-agents")
def remote_agents_api(request: Request):
    require_user(request)
    with db() as conn:
        servers = [dict(row) for row in conn.execute("SELECT id,name,hostname,agent_url,agent_version,agent_fingerprint,registered_at,last_status,last_seen_at,last_error FROM servers WHERE connection_type='agent' ORDER BY name")]
        jobs = [dict(row) for row in conn.execute("SELECT id,server_id,action,state,remote_job_id,created_at,started_at,finished_at,error FROM remote_agent_jobs ORDER BY id DESC LIMIT 100")]
    return {"version": VERSION, "servers": servers, "jobs": jobs}
