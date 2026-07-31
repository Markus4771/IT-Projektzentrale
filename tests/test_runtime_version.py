from pathlib import Path


def test_runtime_version_module_updates_shared_version():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v160.py").read_text(encoding="utf-8")
    runtime = (root / "app/v160_runtime.py").read_text(encoding="utf-8")
    service = (root / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (root / "debian/postinst").read_text(encoding="utf-8")

    assert 'VERSION = "1.6.0"' in source
    assert "base.VERSION = VERSION" in source
    assert "app.version = VERSION" in source
    assert "store_module._upsert_manifest = upsert_manifest" in runtime
    assert "app.v160_runtime:app" in service
    assert '\"version\":\"1.6.0\"' in postinst
