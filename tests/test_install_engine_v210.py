from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v210_release_wiring():
    source = (ROOT / "app/v210.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v210_runtime.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert 'VERSION = "2.1.0"' in source
    assert "app.v200" in source
    assert "app.v311_runtime:app" in service
    assert "app.v320_runtime:app" in service
    assert "app.v330_runtime:app" in service
    assert "app.v331_runtime:app" in service
    assert "app.v340_runtime:app" in service
    assert '\"version\":\"2.5.0\"' in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.4.0"
    assert "app.version = VERSION" in runtime


def test_worker_is_serial_and_guarded():
    worker = (ROOT / "scripts/itpz-install-worker").read_text(encoding="utf-8")
    unit = (ROOT / "systemd/it-projektzentrale-worker.service").read_text(encoding="utf-8")
    assert "BEGIN IMMEDIATE" in worker
    assert "WHERE j.state='queued' ORDER BY j.id LIMIT 1" in worker
    assert "dpkg-deb" in worker
    assert "ITPZ_SYSTEM_HELPER" in worker
    assert "health_check" in worker
    assert "rollback" in worker
    assert "NoNewPrivileges=false" in unit
    assert "ReadWritePaths=/var/lib/it-projektzentrale" in unit
    assert "ExecStartPre=/usr/bin/curl" in unit


def test_install_engine_api_and_ui():
    source = (ROOT / "app/v210.py").read_text(encoding="utf-8")
    queue = (ROOT / "templates/installation_queue.html").read_text(encoding="utf-8")
    detail = (ROOT / "templates/installation_job.html").read_text(encoding="utf-8")
    for endpoint in ("/api/v1/install/jobs", "/installation/jobs/{job_id}"):
        assert endpoint in source
    assert "progress" in source
    assert "Rollback vormerken" in detail
    assert "progress" in queue
