# ChatGPT-Projektkontext – IT-Projektzentrale

## Projektidentität

- Projekt: IT-Projektzentrale
- Repository: `Markus4771/IT-Projektzentrale`
- aktuelle Anwendungsversion: `1.0.0-beta.1`
- Debian-Version: `1.0.0~beta1`
- Paketname und Dienst: `it-projektzentrale`
- Standard-Port: 80 über Nginx
- Anwendung: FastAPI/Uvicorn auf `127.0.0.1:8000`
- Datenbank der Beta 1: SQLite

## Projektziel

Die IT-Projektzentrale soll die zentrale Empfangs-, Installations- und Verwaltungsoberfläche für eigenständige Debian-Projekte werden. Installierte Projekte erscheinen als Kacheln. „Öffnen“ führt zur Projekt-Weboberfläche, „Verwalten“ zu den erlaubten Verwaltungsfunktionen.

## Tatsächlicher Stand

Beta 1 enthält eine funktionsfähige Grundanwendung mit Projektverwaltung, Dashboard, DEB-Upload, GitHub-/Gitea-Releaseabruf, Paketinstallation, Dienststeuerung, Logs, Backups, Manifesten und Systemübersicht. Quellcode, Webtemplates, Nginx- und systemd-Konfiguration sowie ein Debian-Paket sind vorhanden.

Der Funktionsstand ist kleiner als das Lastenheft. Insbesondere fehlen das vollständige Rollenmodell, erzwungener Erstkennwortwechsel, sichere Geheimnisverwaltung, umfassende Paketvorprüfung, verlässlicher Rollback und vollständige Backup-Wiederherstellung.

## Sicherheitsstatus

Beta 1 besitzt bekannte Freigabeblocker. Sie darf nur in einem abgeschotteten Testsystem eingesetzt werden. Maßgeblich ist `docs/security/SECURITY_REVIEW_1.0.0-beta.1.md`.

## Arbeitsweise

- GitHub ist die maßgebliche Projektquelle.
- Änderungen modular umsetzen und mit Tests absichern.
- Keine Funktionen entfernen oder als fertig bezeichnen, solange Abnahmekriterien fehlen.
- Paketinstallationen und Dienstaktionen besonders restriktiv behandeln.
- Geheimnisse niemals in Repository, Oberfläche, URL oder Protokoll schreiben.
- Jede Version benötigt synchronisierte Anwendung, Paketmetadaten, Changelog, Dokumentation und Prüfsumme.

