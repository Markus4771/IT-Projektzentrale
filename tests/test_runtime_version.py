from pathlib import Path


def test_runtime_version_module_updates_shared_version():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v210.py").read_text(encoding="utf-8")
    runtime = (root / "app/v210_runtime.py").read_text(encoding="utf-8")
    service = (root / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (root / "debian/postinst").read_text(encoding="utf-8")

    assert 'VERSION = "2.1.0"' in source
    assert 'VERSION = "2.1.0"' in runtime
    assert "base.VERSION = VERSION" in source
    assert "app.version = VERSION" in runtime
    assert "app.v210_runtime:app" in service
    assert '\"version\":\"2.1.0\"' in postinst
