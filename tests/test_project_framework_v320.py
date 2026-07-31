from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _runtime(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.setenv("ITPZ_SECRET", "x" * 64)
    monkeypatch.setenv("ITPZ_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ITPZ_MASTER_KEY_FILE", str(tmp_path / "master.key"))
    return importlib.import_module("app.v320_runtime")


def test_v320_runtime_imports_real_app(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, monkeypatch)
    assert runtime.VERSION == "3.2.0"
    assert runtime.app.version == "3.2.0"
    assert callable(runtime.app.on_event)


def test_valid_manifest_is_normalized(tmp_path, monkeypatch):
    _runtime(tmp_path, monkeypatch)
    module = importlib.import_module("app.v320")
    manifest, digest = module._parse_manifest_text(
        """schema: itpz/v1
id: contactsync
name: ContactSync Professional
version: 3.2.9
type: deb
channel: stable
category: Kommunikation
package:
  name: contactsync-professional
  asset: contactsync_*.deb
source:
  provider: github
  repository: Markus4771/contactsync
permissions:
  - network
  - database-write
dependencies:
  - id: nextcloud
    optional: true
"""
    )
    assert manifest["id"] == "contactsync"
    assert manifest["package"]["name"] == "contactsync-professional"
    assert manifest["dependencies"][0]["optional"] is True
    assert len(digest) == 64


def test_manifest_rejects_unknown_permission(tmp_path, monkeypatch):
    _runtime(tmp_path, monkeypatch)
    module = importlib.import_module("app.v320")
    with pytest.raises(module.ManifestError, match="Unbekannte Berechtigung"):
        module._parse_manifest_text(
            "schema: itpz/v1\nid: testprojekt\nname: Testprojekt\nversion: 1.0.0\ntype: deb\npermissions: [root-shell]\n"
        )


def test_manifest_rejects_direct_cycle_and_unknown_fields(tmp_path, monkeypatch):
    _runtime(tmp_path, monkeypatch)
    module = importlib.import_module("app.v320")
    with pytest.raises(module.ManifestError):
        module._parse_manifest_text(
            "schema: itpz/v1\nid: testprojekt\nname: Testprojekt\nversion: 1.0.0\ntype: deb\ndependencies: [testprojekt]\n"
        )
    with pytest.raises(module.ManifestError, match="Unbekannte Felder"):
        module._parse_manifest_text(
            "schema: itpz/v1\nid: testprojekt\nname: Testprojekt\nversion: 1.0.0\ntype: deb\nshell: rm -rf /\n"
        )


def test_release_and_packaging_are_wired():
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    nav = (ROOT / "templates/base.html").read_text(encoding="utf-8")
    assert "app.v320_runtime:app" in service
    assert "app.v330_runtime:app" in service
    assert "app.v331_runtime:app" in service
    assert "EXPECTED_VERSION=3.3.1" in postinst
    assert "ITPZ_PROJECT_SCAN_ROOTS" in postinst
    assert "/srv/itpz-projects" in postinst
    assert 'href="/project-framework"' in nav
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.3.1"


def test_project_apply_uses_existing_project_schema():
    source = (ROOT / "app/v320.py").read_text(encoding="utf-8")
    assert "WHERE slug=?" in source
    assert "INSERT INTO projects(name,slug,description,category,status,version,project_url,repo_url,package_name)" in source
    assert "latest_version" not in source
    assert "homepage_url" not in source
