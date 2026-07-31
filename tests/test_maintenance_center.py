from pathlib import Path


def test_maintenance_center_contains_backup_safety_and_updates():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v180.py").read_text(encoding="utf-8")
    assert "source.backup(destination)" in source
    assert "itpz-backup-v1" in source
    assert "member.islnk()" in source
    assert "member.issym()" in source
    assert "backup.pre-update" in source
    assert "run_helper(\"install\"" in source
    assert "CREATE TABLE IF NOT EXISTS backup_plans" in source
    assert "CREATE TABLE IF NOT EXISTS maintenance_jobs" in source


def test_maintenance_routes_and_template_are_present():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v180.py").read_text(encoding="utf-8")
    template = (root / "templates/maintenance.html").read_text(encoding="utf-8")
    for route in ("/maintenance", "/maintenance/backups/create", "/maintenance/restore/validate", "/api/v1/maintenance"):
        assert route in source
    assert "Backup & Updates" in template
    assert "Wiederherstellung prüfen" in template
