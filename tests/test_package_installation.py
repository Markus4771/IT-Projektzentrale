from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_versions_are_consistent() -> None:
    version = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    modules = sorted((ROOT / "app").glob("v*.py"))
    module = modules[-1].read_text(encoding="utf-8") if modules else (ROOT / "app/main.py").read_text(encoding="utf-8")
    postinst = (ROOT / "debian" / "postinst").read_text(encoding="utf-8")

    assert f'VERSION = "{version}"' in module
    assert f"IT-Projektzentrale {version} wurde erfolgreich eingerichtet." in postinst


def test_postinst_repairs_state_permissions_before_start() -> None:
    postinst = (ROOT / "debian" / "postinst").read_text(encoding="utf-8")

    assert "repair_state_permissions" in postinst
    assert 'chown -R "$APP_USER:$APP_USER" "$STATE_DIR"' in postinst
    assert "verify_state_writable" in postinst
    assert 'touch "$1/.write-test"' in postinst
    assert postinst.index("verify_state_writable") < postinst.rindex('systemctl restart "$SERVICE"')


def test_postinst_requires_successful_health_check() -> None:
    postinst = (ROOT / "debian" / "postinst").read_text(encoding="utf-8")

    assert "HEALTH_URL=http://127.0.0.1:8000/health" in postinst
    assert "wait_for_health" in postinst
    assert "journalctl -u" in postinst
    assert "exit 1" in postinst
