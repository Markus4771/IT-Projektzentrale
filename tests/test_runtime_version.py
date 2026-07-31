from pathlib import Path


def test_runtime_version_module_updates_shared_version():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v200.py").read_text(encoding="utf-8")
    service = (root / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (root / "debian/postinst").read_text(encoding="utf-8")

    assert 'VERSION = "2.0.0"' in source
    assert "base.VERSION = VERSION" in source
    assert "app.version = VERSION" in source
    assert "app.v200:app" in service
    assert '\"version\":\"2.0.0\"' in postinst
