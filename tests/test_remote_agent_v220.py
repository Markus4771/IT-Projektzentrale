from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_remote_agent_control_plane_has_security_guards():
    source = (ROOT / "app/v220.py").read_text(encoding="utf-8")
    assert 'ALLOWED_REMOTE_ACTIONS' in source
    assert 'secrets.token_urlsafe(32)' in source
    assert 'hashlib.sha256' in source
    assert 'Authorization' in source
    assert 'require_admin' in source
    assert '/api/v1/remote-agents' in source
    assert 'remote_agent_jobs' in source


def test_agent_is_packaged_and_restricted():
    agent = (ROOT / "agent/itpz-agent.py").read_text(encoding="utf-8")
    unit = (ROOT / "agent/itpz-agent.service").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_agent_deb.sh").read_text(encoding="utf-8")
    for action in ('apt-update','apt-upgrade','backup','install','compose-update','compose-rollback'):
        assert action in agent
    assert "Authorization" in agent
    assert "shell=True" not in agent
    assert "ProtectSystem=strict" in unit
    assert "NoNewPrivileges=false" in unit
    assert "itpz-agent_" in build


def test_version_220_remains_in_release_chain():
    runtime = (ROOT / "app/v220_runtime.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    assert 'VERSION = "2.2.0"' in runtime
    assert 'app.v311_runtime:app' in service
    assert 'app.v320_runtime:app' in service
    assert 'app.v330_runtime:app' in service
    assert 'app.v331_runtime:app' in service
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.3.1"
