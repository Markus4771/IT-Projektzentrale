# IT-Projektzentrale

Die **IT-Projektzentrale** ist eine deutschsprachige Weboberfläche zum Anzeigen, Installieren, Aktualisieren und Verwalten eigener IT-Projekte auf Debian-basierten Systemen.

> **Aktueller Softwarestand:** `1.0.0-beta.2` – gehärteter Teststand, noch nicht für den Produktivbetrieb freigegeben.

## Vorhandener Funktionsstand der Beta 2

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

Der genaue fachliche Zielumfang für Version 1.0 steht im [Lastenheft](docs/requirements/REQUIREMENTS.md). Die Beta 2 erfüllt dieses Lastenheft noch nicht vollständig.

## Sicherheitsverbesserungen in Beta 2

- zufälliges Initialpasswort pro Installation und erzwungener Passwortwechsel
- scrypt-Passworthashes und begrenzte Anmeldeversuche
- sitzungsgebundener CSRF-Schutz für verändernde Webaktionen
- geschützte Sitzungen und Anmeldungspflicht für Dashboard und APIs
- validierender Root-Helfer und root-only systemd-Worker statt direkter breiter `apt-get`- und `systemctl`-Rechte
- getrennte Programm- und Zustandsdaten unter `/opt` und `/var/lib`
- begrenzte, gestreamte Uploads sowie Paketnamen- und Architekturprüfung
- atomare Ablage geprüfter Uploads, root-eigene Helfer-Positivlisten und Browser-Sicherheitsheader
- gehärteter systemd-Dienst und reduzierte Nginx-Uploadgröße

Noch offen sind insbesondere das vollständige Drei-Rollen-Modell, verschlüsselte Tokenablage, Rollback und vollständige Wiederherstellung. Details stehen in [docs/security/SECURITY_REVIEW_1.0.0-beta.2.md](docs/security/SECURITY_REVIEW_1.0.0-beta.2.md).

## Repository-Inhalt

- `app/`, `templates/`, `static/` – Anwendung und Weboberfläche
- `debian/` – Debian-Paketmetadaten und Maintainer-Skripte
- `nginx/`, `systemd/` – Betriebskonfiguration
- `scripts/build_deb.sh` – reproduzierbarer Paketbau
- `docs/requirements/` – Lastenheft, Entscheidungen und offene Fragen
- `docs/security/` – Sicherheitsprüfung
- `.github/workflows/ci.yml` – Syntax-, Paketbau- und Konsistenzprüfung

Die zusätzlich hochgeladenen Beta-1-Dateien dokumentieren nur den ursprünglichen Stand. Künftige Pakete sollen aus dem aktuellen Quellcode gebaut und als GitHub-Release mit Prüfsumme veröffentlicht werden.

## Installation

Die Testinstallation und der geplante öffentliche Release-Weg sind in [docs/INSTALLATION.md](docs/INSTALLATION.md) beschrieben.

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
