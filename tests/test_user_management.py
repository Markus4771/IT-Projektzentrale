from pathlib import Path


def test_user_management_module_is_wired_into_current_release():
    root = Path(__file__).resolve().parents[1]
    user_module = (root / "app/v120.py").read_text(encoding="utf-8")
    v220 = (root / "app/v220.py").read_text(encoding="utf-8")
    v230 = (root / "app/v230.py").read_text(encoding="utf-8")
    v240 = (root / "app/v240.py").read_text(encoding="utf-8")
    v250 = (root / "app/v250.py").read_text(encoding="utf-8")
    v300 = (root / "app/v300.py").read_text(encoding="utf-8")
    v301 = (root / "app/v301.py").read_text(encoding="utf-8")
    v302 = (root / "app/v302.py").read_text(encoding="utf-8")
    release_module = (root / "app/v310.py").read_text(encoding="utf-8")
    service = (root / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    assert "ROLES =" in user_module
    assert "from app.v210_runtime import app" in v220
    assert "from app.v220_runtime import app" in v230
    assert "from app.v230 import app" in v240
    assert "from app.v240 import app" in v250
    assert "from app.v250 import app" in v300
    assert "import app.v300 as v300" in v301
    assert "from app.v301 import app" in v302
    assert "from app.v302 import app" in release_module
    assert "app.v310_runtime:app" in service
    assert (root / "version.txt").read_text(encoding="utf-8").strip() == "3.1.0"


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
    for target in ("/admin/users", "/marketplace", "/app-store", "/plugins", "/servers", "/monitoring", "/compose", "/infrastructure", "/maintenance", "/installation", "/security"):
        assert f'href="{target}"' in template
