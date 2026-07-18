# Architektur – Beta 1 und Zielbild

## Vorhandene Beta-1-Architektur

| Komponente | Aufgabe |
|---|---|
| Nginx | Port 80 und Reverse Proxy auf Uvicorn |
| FastAPI/Uvicorn | Weboberfläche, Routen und JSON-Endpunkte |
| Jinja2 | serverseitige HTML-Templates |
| SQLite | Projekte, Paketquellen, Pakete, Backups und Auditdaten |
| systemd | Betrieb des nicht privilegierten Anwendungsdienstes |
| sudo/apt/systemctl | privilegierte Installation und Dienststeuerung |

Programmdateien liegen unter `/opt/it-projektzentrale`, die Konfiguration unter `/etc/it-projektzentrale.conf`.

## Sicherheitsproblem der Beta 1

Der Anwendungsdienst besitzt über sudo zu breite Befehlsrechte. Das Zielbild benötigt stattdessen einen eng begrenzten, root-eigenen Helfer mit validierten Operationen und Positivlisten. Programmdateien sollen root gehören; nur Daten- und Uploadpfade dürfen für den Dienst schreibbar sein.

## Zielbild

- klar getrennte Webanwendung, Arbeitsaufträge und privilegierte Systemoperationen
- versionierte Datenbankmigrationen
- serverseitiges Rollen- und Projektberechtigungssystem
- verschlüsselte beziehungsweise betriebssystemgeschützte Geheimnisse
- nachvollziehbare Installationsaufträge mit Vorprüfung und Rollback
- getrennte Programm-, Konfigurations-, Daten-, Upload-, Protokoll- und Backup-Pfade

Technische Entscheidungen werden nach Abschluss des Lastenhefts im Pflichtenheft verbindlich festgelegt.

