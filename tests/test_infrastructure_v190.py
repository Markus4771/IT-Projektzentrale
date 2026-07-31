from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v190_release_wiring():
    source = (ROOT / "app/v190.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v190_runtime.py").read_text(encoding="utf-8")
    v200 = (ROOT / "app/v200.py").read_text(encoding="utf-8")
    v210 = (ROOT / "app/v210.py").read_text(encoding="utf-8")
    v220 = (ROOT / "app/v220.py").read_text(encoding="utf-8")
    v230 = (ROOT / "app/v230.py").read_text(encoding="utf-8")
    v240 = (ROOT / "app/v240.py").read_text(encoding="utf-8")
    v250 = (ROOT / "app/v250.py").read_text(encoding="utf-8")
    v300 = (ROOT / "app/v300.py").read_text(encoding="utf-8")
    current = (ROOT / "app/v301.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    assert 'VERSION = "1.9.0"' in source
    assert 'VERSION = "1.9.0"' in runtime
    assert "app.v180_runtime" in runtime
    assert "from app.v190 import app" in v200
    assert "from app.v200 import app" in v210
    assert "from app.v210_runtime import app" in v220
    assert "from app.v220_runtime import app" in v230
    assert "from app.v230 import app" in v240
    assert "from app.v240 import app" in v250
    assert "from app.v250 import app" in v300
    assert "import app.v300 as v300" in current
    assert "app.v301_runtime:app" in service
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.0.1"


def test_infrastructure_has_guardrails():
    source = (ROOT / "app/v190.py").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/itpz-helper").read_text(encoding="utf-8")
    assert "ALLOWED_SERVICE_ACTIONS" in source
    assert "ALLOWED_CONTAINER_ACTIONS" in source
    assert "require_admin" in source
    assert "infrastructure_tasks" in source
    assert "infrastructure_alerts" in source
    assert "container inspect" not in helper
    assert '["/usr/bin/docker", "container", "inspect"' in helper
    assert "apt-upgrade" in helper
    assert "systemd-run" in helper


def test_infrastructure_ui_and_api_are_exposed():
    source = (ROOT / "app/v190.py").read_text(encoding="utf-8")
    base = (ROOT / "templates/base.html").read_text(encoding="utf-8")
    template = (ROOT / "templates/infrastructure.html").read_text(encoding="utf-8")
    assert '@app.get("/infrastructure"' in source
    assert '@app.get("/api/v1/infrastructure")' in source
    assert 'href="/infrastructure"' in base
    assert "Docker-Container" in template
    assert "systemd-Dienste" in template
