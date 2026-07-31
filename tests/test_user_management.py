from pathlib import Path


def test_user_management_module_is_wired_into_current_release():
    root = Path(__file__).resolve().parents[1]
    user_module = (root / "app/v120.py").read_text(encoding="utf-8")
    runtime_module = (root / "app/v180.py").read_text(encoding="utf-8")
    service = (root / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")

    assert "ROLES =" in user_module
    assert "from app.v170 import app" in runtime_module
    assert "app.v180_runtime:app" in service
    assert (root / "version.txt").read_text(encoding="utf-8").strip() == "1.8.0"


def test_user_management_contains_safety_guards():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v120.py").read_text(encoding="utf-8")
    assert "Der letzte aktive Administrator" in source
    assert "Das eigene Konto kann nicht gelöscht werden" in source
    assert "must_change_password=1" in source
    assert all(role in source for role in ("admin", "manager", "viewer"))


def test_navigation_links_platform_areas():
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates/base.html").read_text(encoding="utf-8")
    for target in ("/admin/users", "/app-store", "/plugins", "/servers", "/maintenance"):
        assert f'href="{target}"' in template
