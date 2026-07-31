from pathlib import Path


def test_runtime_version_module_updates_shared_version():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v180.py").read_text(encoding="utf-8")
    runtime = (root / "app/v180_runtime.py").read_text(encoding="utf-8")
    service = (root / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (root / "debian/postinst").read_text(encoding="utf-8")

    assert 'VERSION = "1.8.0"' in source
    assert 'VERSION = "1.8.0"' in runtime
    assert "base.VERSION = VERSION" in source
    assert "app.version = VERSION" in runtime
    assert "app.v180_runtime:app" in service
    assert '\"version\":\"1.8.0\"' in postinst
