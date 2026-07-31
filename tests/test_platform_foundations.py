from pathlib import Path


def test_platform_module_contains_additive_schema_and_api():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v130.py").read_text(encoding="utf-8")

    for table in ("project_repositories", "project_versions", "connectors", "jobs"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in source

    for route in ("/api/v1/platform", "/api/v1/connectors", "/api/v1/jobs"):
        assert route in source

    assert "init_platform_db" in source
    assert "@app.on_event(\"startup\")" in source
    assert "require_admin(request)" in source
    assert "persistent-job-queue" in source


def test_platform_migration_is_additive():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v130.py").read_text(encoding="utf-8")

    assert "DROP TABLE" not in source
    assert "DELETE FROM projects" not in source
    assert source.count("ensure_column(conn, \"projects\"") >= 8
