# IT-Projektzentrale 3.0.0

Die IT-Projektzentrale ist eine deutschsprachige Plattform zur Verwaltung eigener Anwendungen, Debian-Server, Docker-Compose-Projekte, Installationen, Updates, Backups, Monitoring und Plugins.

## Funktionsbereiche

- Projekt- und Benutzerverwaltung mit Rollen
- Software-Center und Installations-Worker mit Health-Checks und Rollback
- lokale und entfernte Debian-Server über den IT-Projektzentrale-Agenten
- Docker-Compose-Verwaltung mit Backup und Rollback
- Infrastrukturübersicht für systemd, Docker, APT, Netzwerk und Speicher
- Monitoring, Alarmregeln, Wartungsfenster, E-Mail und HTTPS-Webhooks
- Marketplace mit Plugin-Lebenszyklus und Abhängigkeiten
- Ed25519-Signaturprüfung für Kataloge und Plugin-Pakete
- verschlüsselte Secret-Ablage mit getrenntem Master-Key
- Sperrlisten für kompromittierte Herausgeber und Pakete
- Audit-, Installations-, Remote-, Monitoring- und Plugin-Protokolle

## Installation

```bash
cd /tmp
wget -O it-projektzentrale_latest_all.deb \
  https://github.com/Markus4771/IT-Projektzentrale/releases/latest/download/it-projektzentrale_latest_all.deb
sudo apt install ./it-projektzentrale_latest_all.deb
```

Danach im Browser öffnen:

```text
http://SERVER-IP/
```

Der Initialzugang einer Neuinstallation liegt unter:

```text
/root/it-projektzentrale-initial-password
```

## Dienste

```text
it-projektzentrale.service
it-projektzentrale-worker.service
it-projektzentrale-monitor.service
```

## Sicherheit

- Webprozess läuft ohne Root-Benutzer.
- Privilegierte Aktionen sind auf feste Root-Helper mit Positivlisten begrenzt.
- Secrets werden mit Fernet verschlüsselt; der Master-Key liegt getrennt unter `/etc/it-projektzentrale.master.key`.
- Marketplace-Kataloge und Pakete werden mit Ed25519 und SHA256 geprüft.
- Nur HTTPS-Quellen sind für automatische Marketplace-Abrufe zulässig.
- Upload- und Downloadgrößen sind begrenzt.
- Archive werden vor Installation auf Pfadausbruch und Links geprüft.

## Entwicklung

```bash
python3 -m pip install -r requirements.txt -r requirements-dev.txt
python3 -m pytest -q
bash scripts/build_deb.sh
bash scripts/build_agent_deb.sh
```

GitHub ist die maßgebliche Projektquelle. Zugangsdaten, Master-Keys, Datenbanken, Backups und produktive Konfigurationen dürfen nicht eingecheckt werden.
