from __future__ import annotations

import importlib
import os
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
    assert runtime.app.version == "3.1.0"


def test_remote_agent_compat_import_does_not_shadow_fastapi_app():
    source = (ROOT / "app/v220_runtime.py").read_text(encoding="utf-8")
    assert "from app import remote_agent_compat as _remote_agent_compat" in source
    assert "import app.remote_agent_compat" not in source


def test_release_wiring_uses_v310_runtime():
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert "app.v310_runtime:app" in service
    assert "EXPECTED_VERSION=3.1.0" in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.1.0"
