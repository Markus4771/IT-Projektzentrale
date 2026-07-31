from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_marketplace_release_is_wired():
    source = (ROOT / "app/v250.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v250_runtime.py").read_text(encoding="utf-8")
    current = (ROOT / "app/v300.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert 'VERSION = "2.5.0"' in source
    assert "from app.v240 import app" in source
    assert "from app.v250 import app" in current
    assert "app.v300_runtime:app" in service
    assert '"version":"2.5.0"' in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.0.0"
    assert "app.version = VERSION" in runtime


def test_marketplace_has_trust_permissions_and_dependencies():
    source = (ROOT / "app/v250.py").read_text(encoding="utf-8")
    template = (ROOT / "templates/marketplace.html").read_text(encoding="utf-8")
    for value in ("marketplace_publishers", "marketplace_packages", "installed_plugins", "plugin_jobs", "/api/v1/marketplace"):
        assert value in source
    assert "publisher_trusted" in source
    assert "Abhängigkeit fehlt oder ist deaktiviert" in source
    assert "PERMISSIONS" in source
    assert "require_admin" in source
    assert "Herausgeber" in template
    assert "Berechtigungen" in template


def test_plugin_helper_is_restricted_and_packaged():
    helper = (ROOT / "scripts/itpz-plugin-helper").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_deb.sh").read_text(encoding="utf-8")
    assert "shell=True" not in helper
    assert "PLUGIN_RE" in helper
    assert "m.issym()" in helper
    assert "m.islnk()" in helper
    assert "relative_to(PACKAGES.resolve())" in helper
    assert "plugin.json" in helper
    assert "itpz-plugin-helper" in build
