from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v352_runtime_and_ui(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.setenv("ITPZ_SECRET", "x" * 64)
    monkeypatch.setenv("ITPZ_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ITPZ_MASTER_KEY_FILE", str(tmp_path / "master.key"))
    runtime = importlib.import_module("app.v352_runtime")
    assert runtime.VERSION == "3.5.2"
    assert runtime.app.version == "3.5.2"
    source = (ROOT / "app/v352.py").read_text(encoding="utf-8")
    template = (ROOT / "templates/github_install.html").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    assert "_sync_source" in source
    assert "_create_plan" in source
    assert "/github-install/prepare" in source
    assert "Repository prüfen und Installationsplan erstellen" in template
    assert "app.v352_runtime:app" in service
    assert "shell=True" not in source


def test_github_install_requires_manifest_release_and_checksum():
    template = (ROOT / "templates/github_install.html").read_text(encoding="utf-8")
    for marker in ("projekt.yaml", "GitHub-Release", "SHA256", "Token"):
        assert marker in template
