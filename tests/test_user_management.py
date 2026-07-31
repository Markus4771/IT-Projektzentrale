from pathlib import Path


def test_user_management_module_is_wired_into_current_release():
    root = Path(__file__).resolve().parents[1]
    user_module = (root / "app/v120.py").read_text(encoding="utf-8")
    runtime_module = (root / "app/v160.py").read_text(encoding="utf-8")
    service = (root / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")

    assert "ROLES =" in user_module
    assert "from app.v150" in runtime_module
    assert "app.v160_runtime:app" in service
    assert (root / "version.txt").read_text(encoding="utf-8").strip() == "1.6.0"


def test_user_management_contains_safety_guards():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v120.py").read_text(encoding="utf-8")
    assert "Der letzte aktive Administrator" in source
    assert "Das eigene Konto kann nicht gelöscht werden" in source
    assert "must_change_password=1" in source
    assert all(role in source for role in ("admin", "manager", "viewer"))


def test_navigation_links_user_management_and_store():
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates/base.html").read_text(encoding="utf-8")
    assert 'href="/admin/users"' in template
    assert 'href="/app-store"' in template
    assert 'href="/plugins"' in template
