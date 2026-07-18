# ChatGPT-Projektkontext – IT-Projektzentrale

## Projektidentität

- Projekt: IT-Projektzentrale
- Repository: `Markus4771/IT-Projektzentrale`
- aktuelle Anwendungsversion: `1.0.0-beta.2`
- Debian-Version: `1.0.0~beta2`
- Paketname und Dienst: `it-projektzentrale`
- Standard-Port: 80 über Nginx
- Anwendung: FastAPI/Uvicorn auf `127.0.0.1:8000`
- Datenbank: SQLite unter `/var/lib/it-projektzentrale/data`

## Projektziel

Die IT-Projektzentrale soll die zentrale Empfangs-, Installations- und Verwaltungsoberfläche für eigenständige Debian-Projekte werden. Installierte Projekte erscheinen als Kacheln. „Öffnen“ führt zur Projekt-Weboberfläche, „Verwalten“ zu den erlaubten Verwaltungsfunktionen.

## Tatsächlicher Stand

Beta 2 enthält die Grundanwendung aus Beta 1 sowie einen sicheren Erstlogin, erzwungenen Passwortwechsel, scrypt-Passworthashes, CSRF-Schutz, Anmeldebegrenzung, geschützte APIs, einen validierenden Root-Helfer, getrennte Datenpfade und erweiterte Paketprüfungen.

Der Funktionsstand ist kleiner als das Lastenheft. Insbesondere fehlen das vollständige Rollenmodell, sichere Geheimnisverwaltung, umfassende Paketvorprüfung, verlässlicher Rollback und vollständige Backup-Wiederherstellung.

## Sicherheitsstatus

Beta 2 ist ein gehärteter Teststand, aber wegen noch fehlendem vollständigem Rollenmodell, Rollback und Wiederherstellung noch nicht produktionsreif. Maßgeblich ist `docs/security/SECURITY_REVIEW_1.0.0-beta.2.md`.

## Arbeitsweise

- GitHub ist die maßgebliche Projektquelle.
- Änderungen modular umsetzen und mit Tests absichern.
- Keine Funktionen entfernen oder als fertig bezeichnen, solange Abnahmekriterien fehlen.
- Paketinstallationen und Dienstaktionen besonders restriktiv behandeln.
- Geheimnisse niemals in Repository, Oberfläche, URL oder Protokoll schreiben.
- Jede Version benötigt synchronisierte Anwendung, Paketmetadaten, Changelog, Dokumentation und Prüfsumme.
