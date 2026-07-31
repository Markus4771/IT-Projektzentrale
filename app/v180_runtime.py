from __future__ import annotations

"""Produktiver Einstiegspunkt für Version 1.8.0."""

import app.main as base
import app.v180 as maintenance
from app.main import db
from app.v180 import app

VERSION = "1.8.0"
base.VERSION = VERSION
app.version = VERSION


def create_maintenance_job(job_type: str, user_id: int | None, project_id: int | None = None) -> int:
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO maintenance_jobs(job_type,project_id,created_by) VALUES(?,?,?)",
            (job_type, project_id, user_id),
        )
        return int(cursor.lastrowid)


maintenance._job = create_maintenance_job
