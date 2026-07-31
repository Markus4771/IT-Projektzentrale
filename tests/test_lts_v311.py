from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v311_runtime_imports_real_fastapi_app(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.setenv("ITPZ_SECRET", "x" * 64)
    monkeypatch.setenv("ITPZ_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ITPZ_MASTER_KEY_FILE", str(tmp_path / "master.key"))
    runtime = importlib.import_module("app.v311_runtime")
    assert runtime.VERSION == "3.1.1"
    assert runtime.app.version == "3.1.1"
    assert hasattr(runtime.app, "router")


def test_lts_installer_orders_services_and_preserves_state():
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert "EXPECTED_VERSION=3.1.1" in postinst
    assert postinst.index('systemctl stop "$WORKER" "$MONITOR" "$SERVICE"') < postinst.index('systemctl start "$SERVICE"')
    assert postinst.index('systemctl start "$SERVICE"') < postinst.index('systemctl start "$WORKER"')
    assert postinst.index('systemctl start "$WORKER"') < postinst.index('systemctl start "$MONITOR"')
    assert "rm -rf /var/lib/it-projektzentrale" not in postinst
    assert "itpz-doctor" in postinst


def test_lts_doctor_and_packaging_are_present():
    doctor = (ROOT / "scripts/itpz-doctor").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_deb.sh").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    assert "PRAGMA integrity_check" in doctor
    assert "monitoring_rules" in doctor
    assert "installation_jobs.phase" in doctor
    assert "itpz-doctor" in build
    assert "app.v311_runtime:app" in service
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.1.1"
