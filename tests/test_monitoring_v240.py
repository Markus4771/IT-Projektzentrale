from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_monitoring_release_is_wired():
    source = (ROOT / "app/v240.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v240_runtime.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert 'VERSION = "2.4.0"' in source
    assert 'VERSION = "2.4.0"' in runtime
    assert "app.v311_runtime:app" in service
    assert "app.v320_runtime:app" in service
    assert '"version":"2.5.0"' in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.2.0"


def test_monitoring_has_rules_alerts_and_windows():
    source = (ROOT / "app/v240.py").read_text(encoding="utf-8")
    template = (ROOT / "templates/monitoring.html").read_text(encoding="utf-8")
    for value in ("monitoring_rules", "monitoring_alerts", "monitoring_runs", "maintenance_windows", "/api/v1/monitoring"):
        assert value in source
    assert "require_admin" in source
    assert "notification_channel == \"webhook\"" in source
    assert "^https://" in source
    assert "Alarmregel anlegen" in template
    assert "Wartungsfenster" in template


def test_monitoring_worker_is_restricted_and_packaged():
    worker = (ROOT / "scripts/itpz-monitor-worker").read_text(encoding="utf-8")
    unit = (ROOT / "systemd/it-projektzentrale-monitor.service").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_deb.sh").read_text(encoding="utf-8")
    assert "shell=True" not in worker
    assert "ITPZ_MONITOR_INTERVAL" in worker
    assert "https://" in worker
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ExecStartPre=/usr/bin/curl" in unit
    assert "itpz-monitor-worker" in build
