from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v230_release_wiring():
    source = (ROOT / "app/v230.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v230_runtime.py").read_text(encoding="utf-8")
    v240 = (ROOT / "app/v240.py").read_text(encoding="utf-8")
    current = (ROOT / "app/v250.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    assert 'VERSION = "2.3.0"' in source
    assert 'VERSION = "2.3.0"' in runtime
    assert "from app.v220_runtime import app" in source
    assert "from app.v230 import app" in v240
    assert "from app.v240 import app" in current
    assert "app.v250_runtime:app" in service
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "2.5.0"


def test_compose_is_path_restricted_and_shell_free():
    source = (ROOT / "app/v230.py").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/itpz-compose-helper").read_text(encoding="utf-8")
    agent = (ROOT / "agent/itpz-agent.py").read_text(encoding="utf-8")
    assert "/srv/itpz-compose" in helper
    assert "relative_to(BASE.resolve())" in helper
    assert "shell=True" not in helper
    assert "shell=True" not in agent
    assert "compose-update" in agent
    assert "compose-rollback" in agent
    assert "tarfile" in helper
    assert "member.issym()" in helper
    assert "SLUG_RE" in source


def test_compose_ui_api_and_packaging():
    source = (ROOT / "app/v230.py").read_text(encoding="utf-8")
    template = (ROOT / "templates/compose.html").read_text(encoding="utf-8")
    nav = (ROOT / "templates/base.html").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_deb.sh").read_text(encoding="utf-8")
    agent_build = (ROOT / "scripts/build_agent_deb.sh").read_text(encoding="utf-8")
    assert '@app.get("/compose"' in source
    assert '@app.get("/api/v1/compose"' in source
    assert 'href="/compose"' in nav
    assert "Rollback" in template
    assert "itpz-compose-helper" in build
    assert "/srv/itpz-compose" in agent_build
