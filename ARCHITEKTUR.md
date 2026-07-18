# Architektur – Beta 2 und Zielbild

## Vorhandene Beta-2-Architektur

| Komponente | Aufgabe | Berechtigungsgrenze |
|---|---|---|
| Nginx | Port 80, Sicherheitsheader und Reverse Proxy | root-eigene Konfiguration |
| FastAPI/Uvicorn | Weboberfläche, Anmeldung, CSRF, Routen und JSON-Endpunkte | eigener unprivilegierter Benutzer |
| Jinja2 und statische Dateien | serverseitige HTML-Ausgabe und Browserlogik | root-eigener Programmcode |
| SQLite | Benutzer, Projekte, Paketquellen, Pakete, Backups und Auditdaten | schreibbarer Zustandsbereich |
| `itpz-helper` | validiert den kleinen, per sudo erlaubten Befehlsumfang | root-eigene öffentliche Schnittstelle |
| `itpz-helper-worker` | führt die erneut geprüfte Aktion als transiente systemd-Unit aus | nur für root ausführbar, außerhalb der Web-Sandbox |
| systemd | Prozessbetrieb und Dateisystem-Härtung | Schreibzugriff nur auf Zustandsdaten |

Programmcode liegt root-eigen unter `/opt/it-projektzentrale`. Die Konfiguration liegt unter `/etc/it-projektzentrale.conf`. Veränderliche Daten liegen unter `/var/lib/it-projektzentrale`; die Positivlisten des privilegierten Helfers getrennt und root-eigen unter `/var/lib/it-projektzentrale-helper`.

## Sicherheitsgrenze der Beta 2

Die Webanwendung darf keine frei zusammengesetzten Root-Befehle starten. `sudo` erlaubt ausschließlich den root-eigenen Helfer. Dieser akzeptiert nur feste Operationen und validierte Argumente. Anschließend startet er einen nur für root ausführbaren Worker als transiente systemd-Unit außerhalb der Web-Sandbox. Der Worker prüft Paketpfad, Paketname, Architektur, Dienstname und Positivlisten erneut.

Diese Grenze ersetzt keine Vertrauensprüfung eines Debian-Pakets. Ein zur Installation freigegebenes DEB kann als root ausgeführte Maintainer-Skripte enthalten. Deshalb dürfen Administratoren nur Pakete aus vertrauenswürdigen Quellen einspielen.

## Noch nicht erreichtes Zielbild

- versionierte Datenbankmigrationen statt eingebetteter Schemaergänzungen
- vollständiges Rollen- und Projektberechtigungssystem
- verschlüsselte oder über einen Secret Store verwaltete Quelltokens
- nachvollziehbare Installationsaufträge mit Fortschritt, Vorprüfung und Rollback
- vollständige Backup-Wiederherstellung und Plattform-Abnahmetests
- verbindlicher HTTPS-Betrieb für öffentliche oder nicht vertrauenswürdige Netze

Technische Entscheidungen werden nach Abschluss des Lastenhefts im Pflichtenheft verbindlich festgelegt.
