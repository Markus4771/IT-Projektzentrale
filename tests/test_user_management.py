from pathlib import Path


def test_version_120_files_are_wired():
    root = Path(__file__).resolve().parents[1]
    assert 'VERSION = "1.2.0"' in (root / "app/v120.py").read_text()
    assert "app.v120:app" in (root / "systemd/it-projektzentrale.service").read_text()
    assert (root / "version.txt").read_text().strip() == "1.2.0"


def test_user_management_contains_safety_guards():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v120.py").read_text()
    assert "Der letzte aktive Administrator" in source
    assert "Das eigene Konto kann nicht gelöscht werden" in source
    assert "must_change_password=1" in source
    assert all(role in source for role in ("admin", "manager", "viewer"))


def test_navigation_links_user_management():
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates/base.html").read_text()
    assert 'href="/admin/users"' in template
