# IT-Projektzentrale

Die **IT-Projektzentrale** ist eine deutschsprachige Weboberfläche zum Anzeigen, Installieren, Aktualisieren und Verwalten eigener IT-Projekte auf Debian-basierten Systemen.

> **Aktueller Softwarestand:** `1.0.0-beta.1` – technischer Teststand, nicht für einen öffentlich erreichbaren oder produktiven Server freigegeben.

## Vorhandener Funktionsstand der Beta 1

- leere Grundinstallation ohne Demo- oder Beispielprojekte
- Dashboard mit installierten Projekten und Direktlinks
- Projektverwaltung mit Archiv und Papierkorb
- lokaler DEB-Upload sowie GitHub- und Gitea-Releasequellen
- Installation, Updateabruf und Deinstallation von Debian-Paketen
- systemd-Steuerung und Journal-Ausgabe
- Projektmanifest-Import und -Export
- Projekt-Backups
- Systemübersicht und Audit-Protokoll
- JSON-Endpunkte unter `/api/v1/projects` und `/api/v1/system`
- Nginx auf Port 80 und systemd-Dienst

Der genaue fachliche Zielumfang für Version 1.0 steht im [Lastenheft](docs/requirements/REQUIREMENTS.md). Die Beta 1 erfüllt dieses Lastenheft noch nicht vollständig.

## Sicherheitsstatus

Die Bestandsprüfung der hochgeladenen Beta 1 hat mehrere Freigabeblocker ergeben:

- bekanntes Initialkennwort `admin/admin` ohne erzwungenen Wechsel
- noch keine vollständige Benutzer- und Rollenverwaltung
- kein vollständiger CSRF-Schutz
- zu weit gefasste sudo-Regeln für Paket- und Dienstaktionen
- Tokens werden noch unverschlüsselt in der lokalen SQLite-Datenbank gespeichert
- fehlende Paket-, Konflikt-, Architektur-, Speicherplatz- und Rollback-Prüfungen

Details stehen in [docs/security/SECURITY_REVIEW_1.0.0-beta.1.md](docs/security/SECURITY_REVIEW_1.0.0-beta.1.md). Die Beta 1 höchstens in einem abgeschotteten Testsystem verwenden.

## Repository-Inhalt

- `app/`, `templates/`, `static/` – Anwendung und Weboberfläche
- `debian/` – Debian-Paketmetadaten und Maintainer-Skripte
- `nginx/`, `systemd/` – Betriebskonfiguration
- `scripts/build_deb.sh` – reproduzierbarer Paketbau
- `docs/requirements/` – Lastenheft, Entscheidungen und offene Fragen
- `docs/security/` – Sicherheitsprüfung
- `.github/workflows/ci.yml` – Syntax-, Paketbau- und Konsistenzprüfung

Die zusätzlich hochgeladenen Dateien `it-projektzentrale_1.0.0-beta.1_all.deb` und `IT-Projektzentrale_1.0.0-beta.1.zip` dokumentieren den ursprünglichen Beta-1-Stand. Künftige Pakete sollen als GitHub-Release mit Prüfsumme veröffentlicht werden.

## Installation

Die aktuelle Testinstallation und der geplante öffentliche Release-Weg sind in [docs/INSTALLATION.md](docs/INSTALLATION.md) beschrieben. Für einen produktiven Server ist die Beta 1 nicht freigegeben.

## Dokumentation

- [Startanweisung für neue Chats](NEUER_CHAT.md)
- [Dauerhafter Projektkontext](CHATGPT_PROJEKTKONTEXT.md)
- [Lastenheft](docs/requirements/REQUIREMENTS.md)
- [Offene Anforderungen](docs/requirements/OPEN_QUESTIONS.md)
- [Entscheidungsprotokoll](docs/requirements/DECISIONS.md)
- [Architektur](ARCHITEKTUR.md)
- [Roadmap](ROADMAP.md)
- [Entwicklungsablauf](docs/development/WORKFLOW.md)
- [Änderungsverlauf](CHANGELOG.md)
- [Projekt-Retrospektive](RETRO.md)

## Repository-Regel

GitHub ist die maßgebliche Projektquelle. Zugangsdaten, Tokens, Passwörter, Datenbanken, Backups, Protokolle und produktive Konfigurationen dürfen niemals eingecheckt werden.

