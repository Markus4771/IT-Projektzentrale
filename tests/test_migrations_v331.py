from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path


def test_v331_repairs_legacy_columns(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    state = tmp_path / "state"
    data = state / "data"
    data.mkdir(parents=True)
    database = data / "projektzentrale.db"
    with sqlite3.connect(database) as conn:
        conn.executescript("""
        CREATE TABLE package_sources (
            id INTEGER PRIMARY KEY,
            project_id INTEGER UNIQUE,
            provider TEXT,
            base_url TEXT,
            repository TEXT,
            token TEXT,
            asset_pattern TEXT,
            enabled INTEGER,
            last_error TEXT
        );
        CREATE TABLE installation_jobs (
            id INTEGER PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'queued'
        );
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT,
            slug TEXT
        );
        """)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setenv("ITPZ_SECRET", "x" * 64)
    monkeypatch.setenv("ITPZ_STATE_DIR", str(state))
    monkeypatch.setenv("ITPZ_MASTER_KEY_FILE", str(tmp_path / "master.key"))
    module = importlib.import_module("app.v331")
    added = module.migrate_schema_v331()
    assert "package_sources.updated_at" in added
    with sqlite3.connect(database) as conn:
        package_columns = {row[1] for row in conn.execute("PRAGMA table_info(package_sources)")}
        job_columns = {row[1] for row in conn.execute("PRAGMA table_info(installation_jobs)")}
        project_columns = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
        assert {"updated_at", "last_error", "asset_pattern"} <= package_columns
        assert {"phase", "progress", "heartbeat_at", "target_version", "backup_path"} <= job_columns
        assert {"service_name", "health_url", "latest_version", "installed_version", "updated_at"} <= project_columns
        assert conn.execute("SELECT 1 FROM schema_migrations WHERE migration_id='3.3.1-required-columns'").fetchone()
    assert module.migrate_schema_v331() == []


def test_release_wiring_keeps_v331_and_uses_v340_runtime():
    root = Path(__file__).resolve().parents[1]
    service = (root / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (root / "debian/postinst").read_text(encoding="utf-8")
    assert "app.v331_runtime:app" in service
    assert "app.v340_runtime:app" in service
    assert "EXPECTED_VERSION=3.4.0" in postinst
    assert (root / "version.txt").read_text(encoding="utf-8").strip() == "3.4.0"
