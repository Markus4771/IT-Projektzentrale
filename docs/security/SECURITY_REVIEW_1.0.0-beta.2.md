# Sicherheitsprüfung 1.0.0-beta.2

Prüfdatum: 18. Juli 2026  
Status: **gehärteter Teststand, noch keine Produktivfreigabe**

## Behobene Beta-1-Blocker

- kein festes `admin/admin` mehr; die Installation erzeugt ein zufälliges Initialpasswort
- Initialpasswort muss beim ersten Login geändert werden
- Passwörter werden mit scrypt und individuellem Salt gespeichert
- wiederholte fehlgeschlagene Anmeldungen werden begrenzt
- verändernde Webaktionen benötigen ein sitzungsgebundenes CSRF-Token
- Dashboard, Paketdownloads und JSON-Endpunkte verlangen eine Anmeldung
- direkte breite sudo-Regeln wurden durch einen validierenden Root-Helfer ersetzt
- privilegierte Aktionen laufen über einen root-only Worker außerhalb der gehärteten Webdienst-Sandbox
- Pakete und Dienste müssen in getrennten, root-eigenen Positivlisten stehen
- Programmcode ist root-eigen; Zustandsdaten liegen getrennt unter `/var/lib`
- Uploads werden gestreamt, größenbegrenzt und auf Name, Paketmetadaten und Architektur geprüft
- geprüfte Uploads ersetzen vorhandene Pakete erst atomar; Nginx setzt CSP und weitere Browser-Sicherheitsheader
- Backups und Exporte besitzen einen freigegebenen systemd-Schreibpfad

Der Root-Helfer schützt vor frei zusammengesetzten `apt-get`- und `systemctl`-Aufrufen. Er kann die grundsätzliche Root-Vertrauensstellung eines installierten Debian-Pakets nicht aufheben. Deshalb dürfen ausschließlich Pakete aus vertrauenswürdigen Quellen installiert werden.

## Noch offene Freigabepunkte

- Projektverwalter und Benutzer mit Lesezugriff vollständig umsetzen
- Tokens zusätzlich verschlüsseln oder über einen spezialisierten Secret Store verwalten
- Update-Sicherung und automatischen Rollback fertigstellen
- vollständige Backup-Wiederherstellung und Datenmigration testen
- Abhängigkeits- und Konfliktprüfung in der Weboberfläche ausbauen
- HTTPS-Betrieb und sichere Cookies für öffentliche Netze verbindlich dokumentieren
- produktive Installation auf den festzulegenden Debian- und Raspberry-Pi-Plattformen testen

## Ergebnis

Beta 2 reduziert die unmittelbar ausnutzbaren Risiken der Beta 1 deutlich. Eine Produktivfreigabe erfolgt erst nach Abschluss der verbleibenden Rollen-, Update-, Wiederherstellungs- und Plattformtests.
