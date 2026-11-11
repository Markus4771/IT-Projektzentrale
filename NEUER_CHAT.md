# Neuer Chat – IT-Projektzentrale

## Startanweisung für eine neue KI-Unterhaltung

Kopiere den folgenden Text in einen neuen Chat:

> Wir entwickeln das GitHub-Projekt `Markus4771/IT-Projektzentrale` weiter. GitHub (`main`) ist die maßgebliche Quelle. Bitte lies zuerst `AGENTS.md`, `NEUER_CHAT.md` und `CHATGPT_PROJEKTKONTEXT.md`.
>
> Lies anschließend `version.txt`, `README.md`, `ARCHITEKTUR.md`, `ROADMAP.md`, `CHANGELOG.md`, `docs/requirements/REQUIREMENTS.md`, `docs/requirements/OPEN_QUESTIONS.md`, `docs/requirements/DECISIONS.md` und die aktuelle Sicherheitsprüfung unter `docs/security/`.
>
> Prüfe den tatsächlichen Quellcode, die Tests, die Debian-Paketierung und vorhandene GitHub-Releases. Gib mir zuerst eine kurze Übersicht über aktuelle Version, implementierte Funktionen, Testergebnisse, Sicherheitsrisiken, offene Punkte und den sinnvollsten nächsten Entwicklungsschritt.
>
> Entwickle danach ausschließlich auf Grundlage des aktuellen Repository-Stands weiter. Unterscheide strikt zwischen implementiert, getestet, geplant und noch nicht geprüft. Ändere nichts Produktives ohne ausdrückliche Freigabe. Pflege Quellcode, Tests, Dokumentation, Versionsdatei und Debian-Paketierung konsistent. Erstelle bei Bedarf einen Pull Request und veröffentliche Releases erst nach erfolgreicher Prüfung.

## Projektidentität

- **Projekt:** IT-Projektzentrale
- **Repository:** https://github.com/Markus4771/IT-Projektzentrale
- **Branch:** `main`
- **Dokumentierter Stand am 11.11.2026:** `1.0.0-beta.2`
- **Debian-Paketversion:** `1.0.0~beta2`
- **Status:** Testversion, noch nicht produktionsreif
- **Bereitstellung:** Nginx Port 80, FastAPI/Uvicorn intern auf `127.0.0.1:8000`

## Projektziel

Zentrale Verwaltungs- und Installationsoberfläche für eigene Anwendungen. Eine Neuinstallation startet ohne Beispielprojekte. Installierte Projekte werden auf dem Dashboard als Kacheln angezeigt; **Öffnen** führt zur hinterlegten Projekt-Webseite und **Verwalten** zur internen Projektverwaltung.

Geplante beziehungsweise schrittweise auszubauende Bereiche: Projektverwaltung, GitHub-/Gitea-Import, Debian-Pakete, Updates, Backups und Wiederherstellung, Dienststatus, Dokumentation, Benutzerrollen und Plugin-System. Den Umsetzungsstand immer im Code verifizieren.

## Wichtige offene Arbeiten

1. Vollständiges Rollen- und Berechtigungsmodell
2. Sichere Token- und Geheimnisverwaltung
3. Paketvorprüfung und sichere Installationsfreigabe
4. Verlässliches Update-Rollback
5. Vollständige Backup-Wiederherstellung und Tests
6. Sicherheitstests und Abnahme vor Produktivbetrieb

## Regeln für weitere Entwicklungsarbeiten

- GitHub-Inhalt zuerst prüfen; nicht auf frühere Chat-Aussagen als alleinige Quelle vertrauen.
- Keine bestehenden Projekte oder Daten automatisch löschen.
- Keine Beispielprojekte bei einer Neuinstallation anlegen.
- Keine Zugangsdaten oder Tokens in Git, Logs oder Beispieldateien speichern.
- Debian-Installation, Nginx-Konfiguration, systemd und Datenbankmigrationen testen.
- Neue Funktionen mit automatisierten Tests und nachvollziehbaren Abnahmekriterien ergänzen.
- Bei einem Release Versionsnummer, Changelog, Paketmetadaten, Build-Artefakte und SHA-256-Prüfsumme abgleichen.
- Den aktuellen Sicherheitsstatus in `docs/security/` beachten.
- Nach jedem Entwicklungsschritt festhalten, was tatsächlich geändert und erfolgreich geprüft wurde.
