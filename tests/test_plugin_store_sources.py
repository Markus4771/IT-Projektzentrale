from pathlib import Path


def test_plugin_framework_security_guards_present():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v150.py").read_text(encoding="utf-8")
    assert "yaml.safe_load" in source
    assert "MAX_MANIFEST_BYTES" in source
    assert "ALLOWED_CAPABILITIES" in source
    assert "PLUGIN_ID_RE" in source
    assert "Nur YAML-Manifeste" in source


def test_app_store_catalog_and_api_are_wired():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v160.py").read_text(encoding="utf-8")
    template = (root / "templates/app_store.html").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS app_catalogs" in source
    assert "CREATE TABLE IF NOT EXISTS app_catalog_entries" in source
    assert '@app.get("/app-store"' in source
    assert '@app.get("/api/v1/app-store")' in source
    assert "validate_manifest(raw)" in source
    assert "Ins Software-Center übernehmen" in template
    assert "PyYAML==6.0.2" in requirements


def test_corrected_plugin_upsert_has_matching_placeholders():
    root = Path(__file__).resolve().parents[1]
    runtime = (root / "app/v160_runtime.py").read_text(encoding="utf-8")
    assert "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)" in runtime
    assert "plugin_module._upsert_manifest = upsert_manifest" in runtime
    assert "store_module._upsert_manifest = upsert_manifest" in runtime
