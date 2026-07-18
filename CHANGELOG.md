# Änderungsverlauf

## [Unveröffentlicht]

## [1.0.0-beta.2] – 2026-07-18

### Sicherheit

- zufälliges Initialpasswort mit zwingendem Wechsel beim ersten Login
- scrypt-Passworthashes und zeitlich begrenzte Anmeldesperre
- CSRF-Schutz für alle verändernden Aktionen
- Anmeldungspflicht für Dashboard, Projektdaten und APIs
- validierender Root-Helfer mit verwalteten Paket- und Dienstlisten
- root-only systemd-Worker für privilegierte Aktionen außerhalb der Webdienst-Sandbox
- sichere Trennung von Programm- und Zustandsdaten
- Uploadgrößen-, Dateinamen-, Paketnamen- und Architekturprüfung
- sicherere Sitzungs- und systemd-Konfiguration
- root-eigene Positivlisten und Browser-Sicherheitsheader

### Behoben

- fehlende Schreibpfade für Backups und Exporte
- fehlerhafte Quellinstallation mit nicht vorhandenen Verzeichnissen
- frei eintragbare unsichere URL-Schemas
- unnötige manuelle Versionsangabe beim DEB-Upload
- mögliches Überschreiben eines vorhandenen Pakets vor abgeschlossener Uploadprüfung

### Tests

- automatisierte Prüfung von Passwort-Hashing, CSRF, Erstlogin und Passwortwechsel
- CI prüft Anwendung, Root-Helfer, Shellskripte, Paketbau und Prüfsumme

### Hinzugefügt

- sichtbarer Quellcode statt ausschließlich eingebetteter ZIP-Datei
- rekonstruierte Debian-Paketquellen und Paketbauskript
- CI für Python-, Shell-, Versions- und Paketprüfungen
- vollständige Übergabe- und Weiterentwicklungsdokumentation
- dokumentierte Sicherheitsprüfung der Beta 1

## [1.0.0-beta.1] – 2026-07-18

### Hinzugefügt

- leere Grundinstallation
- Dashboard mit installierten Projekten und Direktlinks
- Projektverwaltung mit Archiv und Papierkorb
- GitHub-, Gitea- und lokale DEB-Quellen
- Installation, Updateabruf und Deinstallation
- systemd-Steuerung, Logs und Systemübersicht
- Projekt-Backups und Manifest-Import/-Export
- JSON-Endpunkte und Audit-Protokoll
- Debian-Paket für Architektur `all`

### Bekannte Einschränkungen

- Lastenheft noch nicht vollständig umgesetzt
- Benutzer-, Rollen- und Erstkennwortkonzept unvollständig
- Sicherheitsfreigabe ausstehend
