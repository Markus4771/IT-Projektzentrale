from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v351_remote_source_management_is_wired():
    source = (ROOT / "app/v351.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v351_runtime.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    assert 'VERSION = "3.5.1"' in source
    assert 'VERSION = "3.5.1"' in runtime
    assert "app.v351_runtime:app" in service
    for route in (
        '/project-framework/remotes/{source_id}/test',
        '/project-framework/remotes/{source_id}/edit',
        '/project-framework/remotes/{source_id}/delete',
        '/project-framework/remotes/sync-all',
    ):
        assert route in source
    assert "shell=True" not in source


def test_v351_remote_source_ui_has_all_controls():
    template = (ROOT / "templates/project_remote_sources.html").read_text(encoding="utf-8")
    for text in (
        "Neue Quelle hinzufügen",
        "Quelle anlegen",
        "Verbindung testen",
        "Synchronisieren",
        "Bearbeiten",
        "Änderungen speichern",
        "Quelle endgültig löschen",
        "Alle synchronisieren",
        "Synchronisationsprotokoll",
    ):
        assert text in template
