from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_keeps_fastapi_app_object(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.setenv("ITPZ_SECRET", "x" * 64)
    monkeypatch.setenv("ITPZ_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ITPZ_MASTER_KEY_FILE", str(tmp_path / "master.key"))
    runtime = importlib.import_module("app.v310_runtime")
    assert runtime.VERSION == "3.1.0"
    assert callable(runtime.app.on_event)


def test_remote_agent_compat_import_does_not_shadow_fastapi_app():
    source = (ROOT / "app/v220_runtime.py").read_text(encoding="utf-8")
    assert "from app import remote_agent_compat as _remote_agent_compat" in source
    code_lines = [line.strip() for line in source.splitlines() if not line.lstrip().startswith(("#", '"'))]
    assert "import app.remote_agent_compat" not in code_lines


def test_release_wiring_advances_to_v330_runtime():
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert "app.v310_runtime:app" in service
    assert "app.v311_runtime:app" in service
    assert "app.v320_runtime:app" in service
    assert "app.v330_runtime:app" in service
    assert "EXPECTED_VERSION=3.3.0" in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.3.0"
