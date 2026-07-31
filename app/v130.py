from __future__ import annotations

"""Version 1.3.0: Plattform-Grundlagen.

Dieses Modul erweitert die bestehende Projektzentrale um drei bewusst kleine,
stabile Fundamente:

* ein erweiterbares Projektdatenmodell,
* ein einheitliches Connector-Register,
* eine persistente Job-Warteschlange.

Die eigentlichen Connectoren und Job-Worker werden in späteren Versionen als
Module ergänzt. Der Kern speichert nur Konfiguration, Fähigkeiten und Zustand.
"""

import json
import sqlite3
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

import app.main as base
from app.main import audit, db, ensure_column, require_admin, require_user
from app.v121 import app

VERSION = "1.3.0"
base.VERSION = VERSION
app.version = VERSION

PROJECT_STATUSES = {
    "idea",
    "planning",
    "development",
    "testing",
    "production",
    "archived",
}
PROJECT_PRIORITIES = {"low", "normal", "high", "critical"}
JOB_STATES = {"queued", "running", "succeeded", "failed", "cancelled"}


class ConnectorCreate(BaseModel):
    connector_type: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_.-]+$")
    name: str = Field(min_length=2, max_length=100)
    configuration: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True


class JobCreate(BaseModel):
    job_type: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_.-]+$")
    project_id: int | None = None
    connector_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def init_platform_db() -> None:
    """Führt ausschließlich additive, wiederholbare Migrationen aus."""
    with db() as conn:
        ensure_column(conn, "projects", "long_description", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "projects", "priority", "TEXT NOT NULL DEFAULT 'normal'")
        ensure_column(conn, "projects", "tags_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(conn, "projects", "owner_user_id", "INTEGER")
        ensure_column(conn, "projects", "icon", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "projects", "screenshot", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "projects", "install_type", "TEXT NOT NULL DEFAULT 'deb'")
        ensure_column(conn, "projects", "install_status", "TEXT NOT NULL DEFAULT 'not_installed'")
        ensure_column(conn, "projects", "updated_at", "TEXT")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS project_repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                repository TEXT NOT NULL,
                default_branch TEXT NOT NULL DEFAULT 'main',
                web_url TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, provider, repository),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS project_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                version TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'stable',
                source TEXT NOT NULL DEFAULT 'manual',
                released_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, version, channel),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS connectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connector_type TEXT NOT NULL,
                name TEXT NOT NULL,
                configuration_json TEXT NOT NULL DEFAULT '{}',
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'unknown',
                last_checked_at TEXT,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(connector_type, name)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'queued',
                project_id INTEGER,
                connector_id INTEGER,
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
                FOREIGN KEY(connector_id) REFERENCES connectors(id) ON DELETE SET NULL,
                FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_state_created ON jobs(state, created_at);
            CREATE INDEX IF NOT EXISTS idx_connectors_type ON connectors(connector_type);
            CREATE INDEX IF NOT EXISTS idx_project_repositories_project ON project_repositories(project_id);
            """
        )


@app.on_event("startup")
def initialize_v130() -> None:
    init_platform_db()


def _decode(row: sqlite3.Row, *fields: str) -> dict[str, Any]:
    item = dict(row)
    for field in fields:
        raw = item.pop(field, None)
        item[field.removesuffix("_json")] = json.loads(raw or "{}" if field == "configuration_json" else raw or "[]")
    return item


@app.get("/api/v1/platform")
def platform_info(request: Request):
    require_user(request)
    return {
        "version": VERSION,
        "project_statuses": sorted(PROJECT_STATUSES),
        "project_priorities": sorted(PROJECT_PRIORITIES),
        "job_states": sorted(JOB_STATES),
        "features": ["project-model-v2", "connector-registry", "persistent-job-queue"],
    }


@app.get("/api/v1/connectors")
def list_connectors(request: Request):
    require_user(request)
    with db() as conn:
        rows = conn.execute("SELECT * FROM connectors ORDER BY connector_type,name").fetchall()
    return [_decode(row, "configuration_json", "capabilities_json") for row in rows]


@app.post("/api/v1/connectors", status_code=201)
def create_connector(payload: ConnectorCreate, request: Request):
    require_admin(request)
    try:
        with db() as conn:
            cursor = conn.execute(
                """INSERT INTO connectors(
                    connector_type,name,configuration_json,capabilities_json,enabled
                ) VALUES(?,?,?,?,?)""",
                (
                    payload.connector_type,
                    payload.name.strip(),
                    json.dumps(payload.configuration, ensure_ascii=False, sort_keys=True),
                    json.dumps(sorted(set(payload.capabilities)), ensure_ascii=False),
                    int(payload.enabled),
                ),
            )
            connector_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM connectors WHERE id=?", (connector_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Connector mit diesem Typ und Namen existiert bereits") from exc
    audit("connector.created", None, f"{payload.connector_type}:{payload.name}")
    return _decode(row, "configuration_json", "capabilities_json")


@app.get("/api/v1/jobs")
def list_jobs(request: Request, state: str | None = None, limit: int = 50):
    require_user(request)
    limit = max(1, min(limit, 200))
    if state is not None and state not in JOB_STATES:
        raise HTTPException(400, "Ungültiger Job-Status")
    with db() as conn:
        if state:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE state=? ORDER BY id DESC LIMIT ?", (state, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_decode(row, "payload_json", "result_json") for row in rows]


@app.post("/api/v1/jobs", status_code=202)
def enqueue_job(payload: JobCreate, request: Request):
    user = require_admin(request)
    with db() as conn:
        if payload.project_id is not None and not conn.execute(
            "SELECT 1 FROM projects WHERE id=?", (payload.project_id,)
        ).fetchone():
            raise HTTPException(404, "Projekt nicht gefunden")
        if payload.connector_id is not None and not conn.execute(
            "SELECT 1 FROM connectors WHERE id=?", (payload.connector_id,)
        ).fetchone():
            raise HTTPException(404, "Connector nicht gefunden")
        cursor = conn.execute(
            """INSERT INTO jobs(job_type,project_id,connector_id,payload_json,created_by)
               VALUES(?,?,?,?,?)""",
            (
                payload.job_type,
                payload.project_id,
                payload.connector_id,
                json.dumps(payload.payload, ensure_ascii=False, sort_keys=True),
                user["id"],
            ),
        )
        job_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    audit("job.queued", payload.project_id, f"{payload.job_type} #{job_id}")
    return _decode(row, "payload_json", "result_json")
