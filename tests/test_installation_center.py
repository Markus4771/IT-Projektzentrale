from pathlib import Path


def test_installation_center_routes_and_tables_exist():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v200.py").read_text(encoding="utf-8")
    for table in ("installation_jobs", "installation_settings"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in source
    for route in (
        '/installation/catalog', '/installation/sources', '/installation/updates',
        '/installation/queue', '/api/v1/installation',
    ):
        assert route in source


def test_installation_center_has_safety_guards():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v200.py").read_text(encoding="utf-8")
    assert "require_admin(request)" in source
    assert "ALLOWED_PROVIDERS" in source
    assert "ALLOWED_JOB_TYPES" in source
    assert "REPOSITORY_RE.fullmatch" in source
    assert "state IN ('queued','running')" in source


def test_installation_templates_are_complete():
    root = Path(__file__).resolve().parents[1]
    main = (root / "templates/installation.html").read_text(encoding="utf-8")
    assert "Installationszentrum" in main
    for path in ("catalog", "sources", "updates", "queue"):
        assert f'/installation/{path}' in main
        assert (root / f"templates/installation_{path}.html").exists()
