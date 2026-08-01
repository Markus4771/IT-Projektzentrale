from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v350_runtime_and_release_wiring(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.setenv("ITPZ_SECRET", "x" * 64)
    monkeypatch.setenv("ITPZ_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ITPZ_MASTER_KEY_FILE", str(tmp_path / "master.key"))
    runtime = importlib.import_module("app.v350_runtime")
    assert runtime.VERSION == "3.5.0"
    assert runtime.app.version == "3.5.0"
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert "app.v350_runtime:app" in service
    assert "app.v340_runtime:app" in service
    assert "EXPECTED_VERSION=3.5.0" in postinst
    assert '"version":"3.4.0"' in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.5.0"


def test_manifest_installation_has_explicit_approval_and_guardrails():
    source = (ROOT / "app/v350.py").read_text(encoding="utf-8")
    for value in (
        "manifest_install_plans",
        "requested_permissions",
        "approved_permissions",
        "dependency_plan",
        "DANGEROUS_PERMISSIONS",
        "Nicht auflösbare Abhängigkeiten",
        "Nicht alle angeforderten Berechtigungen",
        "_download_asset",
        "installation_jobs",
        "rollback_enabled",
        "/api/v1/manifest-installation",
    ):
        assert value in source
    assert "shell=True" not in source


def test_manifest_installation_ui_is_packaged_and_linked():
    overview = (ROOT / "templates/manifest_installation.html").read_text(encoding="utf-8")
    detail = (ROOT / "templates/manifest_installation_plan.html").read_text(encoding="utf-8")
    nav = (ROOT / "templates/base.html").read_text(encoding="utf-8")
    assert "Installationsplan erstellen" in overview
    assert "Berechtigungen freigeben" in detail
    assert "Installation starten" in detail
    assert 'href="/manifest-installation"' in nav
