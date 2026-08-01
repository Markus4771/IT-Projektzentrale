from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v190_release_wiring():
    source = (ROOT / "app/v190.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v190_runtime.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    assert 'VERSION = "1.9.0"' in source
    assert 'VERSION = "1.9.0"' in runtime
    assert "app.v180_runtime" in runtime
    assert "app.v311_runtime:app" in service
    assert "app.v320_runtime:app" in service
    assert "app.v330_runtime:app" in service
    assert "app.v331_runtime:app" in service
    assert "app.v340_runtime:app" in service
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.4.0"


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
