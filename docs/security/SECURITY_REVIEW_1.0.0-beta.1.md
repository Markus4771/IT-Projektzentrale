# Sicherheitsprüfung 1.0.0-beta.1

Prüfdatum: 18. Juli 2026  
Status: **nicht für Produktivbetrieb oder öffentlichen Zugriff freigegeben**

## Geprüfte Artefakte

- `it-projektzentrale_1.0.0-beta.1_all.deb`
- `IT-Projektzentrale_1.0.0-beta.1.zip`
- Quellcode und Debian-Maintainer-Skripte

Die Archive sind formal lesbar. Quellcode im ZIP und unter `/opt/it-projektzentrale` im DEB stimmen überein. Python-, Bash- und POSIX-Shell-Syntax sind gültig.

## Kritische Freigabeblocker

1. Das bekannte Konto `admin/admin` wird eingerichtet; ein erzwungener Wechsel fehlt.
2. Der Dienst darf über sudo beliebige passende `apt-get remove`- und `systemctl`-Operationen ausführen.
3. Verändernde Formulare besitzen keinen vollständigen CSRF-Schutz.
4. Das geforderte Benutzer- und Rollenmodell ist noch nicht umgesetzt.
5. GitHub-/Gitea-Tokens werden unverschlüsselt in SQLite gespeichert.
6. Die Paketinstallation führt hochgeladene DEB-Maintainer-Skripte als Root aus, ohne die im Lastenheft geforderten Vorprüfungen vollständig umzusetzen.

## Weitere wesentliche Punkte

- öffentliche JSON-Endpunkte geben Projekt- und Systemdaten aus
- keine Anmeldebegrenzung gegen wiederholte Kennwortversuche
- Web-, Repository- und Dokumentations-URLs werden nicht auf sichere Schemas begrenzt
- Upload wird vollständig in den Arbeitsspeicher gelesen; Nginx erlaubt bis zu 2 GiB
- keine vollständige Prüfung von Architektur, Abhängigkeiten, Konflikten und Speicherplatz
- kein verlässlicher Rollback nach fehlgeschlagenem Update
- Backups können erstellt, aber nicht vollständig wiederhergestellt werden
- Python-Abhängigkeiten werden im `postinst` als Root aus dem Netz installiert
- ZIP und DEB enthalten ein unnötiges Python-Bytecode-Artefakt
- Quellcode gehört nach Installation dem Dienstkonto, obwohl nur Datenpfade schreibbar sein sollten
- der systemd-Schutz erlaubt Schreibzugriff nur auf `data` und `uploads`, während die Anwendung zusätzlich `backups` und `exports` anlegen muss; dadurch kann der Dienststart fehlschlagen
- das mitgelieferte `install.sh` kopiert nicht vorhandene Verzeichnisse `data` und `uploads` und kann deshalb bei einer Quellinstallation abbrechen

## Freigabekriterien für Beta 2

- sicherer Erstlogin mit zwingendem Kennwortwechsel
- serverseitige Benutzer-, Rollen- und Projektberechtigungen
- CSRF-Schutz und Anmeldebegrenzung
- root-eigener Systemhelfer mit festen Operationen und Positivlisten
- geschützte Tokenablage und maskierte Fehlerausgaben
- begrenzte, gestreamte Uploads und vollständige Paketmetadatenprüfung
- abgesicherte API und URL-Validierung
- automatisierte Tests der kritischen Verwaltungsaktionen
- reproduzierbares DEB ohne Bytecode- und Laufzeitdateien
