from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v340_runtime_and_release_wiring(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.setenv("ITPZ_SECRET", "x" * 64)
    monkeypatch.setenv("ITPZ_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ITPZ_MASTER_KEY_FILE", str(tmp_path / "master.key"))
    runtime = importlib.import_module("app.v340_runtime")
    assert runtime.VERSION == "3.4.0"
    assert runtime.app.version == "3.4.0"
    assert hasattr(importlib.import_module("app.v320"), "_apply_manifest")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert "app.v340_runtime:app" in service
    assert "EXPECTED_VERSION=3.4.0" in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.4.0"


def test_repository_catalog_has_guardrails_and_pagination():
    source = (ROOT / "app/v340.py").read_text(encoding="utf-8")
    for marker in (
        "repository_accounts", "discovered_repositories", "repository_discovery_runs",
        "MAX_PAGES", "include_forks", "include_archived", "_safe_https_base",
        "/api/v1/repository-catalog", "/repository-catalog/accounts/{account_id}/discover",
    ):
        assert marker in source
    assert "shell=True" not in source
    assert "Authorization" in source
    assert "MAX_MANIFEST" in source


def test_project_sdk_is_documented_validatable_and_packaged():
    source = (ROOT / "app/v340.py").read_text(encoding="utf-8")
    template = (ROOT / "templates/project_sdk.html").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_deb.sh").read_text(encoding="utf-8")
    nav = (ROOT / "templates/base.html").read_text(encoding="utf-8")
    assert "/project-sdk/validate" in source
    assert "/project-sdk/projekt.yaml" in source
    assert "projekt.yaml herunterladen" in template
    assert 'href="/repository-catalog"' in nav
    assert 'href="/project-sdk"' in nav
    assert '"$ROOT_DIR/sdk"' in build
    assert "PROJECT_SDK.md" in build
    assert (ROOT / "sdk/projekt.example.yaml").is_file()
    assert (ROOT / "docs/PROJECT_SDK.md").is_file()


def test_apply_helper_uses_parameterized_sql_and_health_metadata():
    helper = (ROOT / "app/v340_apply.py").read_text(encoding="utf-8")
    assert "service_name" in helper
    assert "health_url" in helper
    assert "installation_status" in helper
    assert "shell=True" not in helper
    assert "framework._apply_manifest = apply_manifest" in helper
