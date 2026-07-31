from __future__ import annotations

"""Version 3.3.1: idempotente Datenbankmigrationen für ältere Installationen."""

import os
import sqlite3
from pathlib import Path
from typing import Iterable

import app.main as base
from app.main import audit
from app.v330 import app

VERSION = "3.3.1"
base.VERSION = VERSION
app.version = VERSION

_REQUIRED_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "package_sources": (
        ("provider", "TEXT NOT NULL DEFAULT ''"),
        ("base_url", "TEXT NOT NULL DEFAULT ''"),
        ("repository", "TEXT NOT NULL DEFAULT ''"),
        ("token", "TEXT NOT NULL DEFAULT ''"),
        ("asset_pattern", "TEXT NOT NULL DEFAULT '*.deb'"),
        ("enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("last_error", "TEXT NOT NULL DEFAULT ''"),
        ("updated_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ),
    "installation_jobs": (
        ("phase", "TEXT NOT NULL DEFAULT 'queued'"),
        ("progress", "INTEGER NOT NULL DEFAULT 0"),
        ("worker_id", "TEXT NOT NULL DEFAULT ''"),
        ("heartbeat_at", "TEXT"),
        ("target_version", "TEXT NOT NULL DEFAULT ''"),
        ("previous_version", "TEXT NOT NULL DEFAULT ''"),
        ("backup_path", "TEXT NOT NULL DEFAULT ''"),
        ("rollback_state", "TEXT NOT NULL DEFAULT ''"),
    ),
    "projects": (
        ("service_name", "TEXT NOT NULL DEFAULT ''"),
        ("health_url", "TEXT NOT NULL DEFAULT ''"),
        ("latest_file", "TEXT NOT NULL DEFAULT ''"),
        ("latest_version", "TEXT NOT NULL DEFAULT ''"),
        ("installed_version", "TEXT NOT NULL DEFAULT ''"),
        ("installation_status", "TEXT NOT NULL DEFAULT ''"),
        ("updated_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ),
}


def _migration_db() -> sqlite3.Connection:
    """Öffnet bewusst den aktuell konfigurierten State-Pfad.

    Dadurch funktionieren Upgrades und isolierte Regressionstests auch dann,
    wenn app.main bereits zuvor mit einem anderen ITPZ_STATE_DIR importiert wurde.
    """
    state = Path(os.getenv("ITPZ_STATE_DIR", "/var/lib/it-projektzentrale"))
    database = state / "data" / "projektzentrale.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _add_missing_columns(
    conn: sqlite3.Connection, table: str, columns: Iterable[tuple[str, str]]
) -> list[str]:
    if not _table_exists(conn, table):
        return []
    existing = _column_names(conn, table)
    added: list[str] = []
    for name, definition in columns:
        if name in existing:
            continue
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
        added.append(f"{table}.{name}")
    return added


def migrate_schema_v331() -> list[str]:
    """Repariert ältere Schemas transaktional und kann beliebig oft laufen."""
    with _migration_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            details TEXT NOT NULL DEFAULT ''
        )""")
        added: list[str] = []
        for table, columns in _REQUIRED_COLUMNS.items():
            added.extend(_add_missing_columns(conn, table, columns))
        conn.execute(
            """INSERT INTO schema_migrations(migration_id,details)
               VALUES('3.3.1-required-columns',?)
               ON CONFLICT(migration_id) DO UPDATE SET
               applied_at=CURRENT_TIMESTAMP,details=excluded.details""",
            (",".join(added) if added else "schema already complete",),
        )
        if _table_exists(conn, "installation_jobs"):
            conn.execute("UPDATE installation_jobs SET phase=COALESCE(NULLIF(phase,''),state,'queued')")
            conn.execute("UPDATE installation_jobs SET progress=CASE WHEN progress<0 THEN 0 WHEN progress>100 THEN 100 ELSE progress END")
    return added


@app.on_event("startup")
def initialize_v331() -> None:
    added = migrate_schema_v331()
    if added:
        audit("database.schema_repaired", None, ",".join(added))
