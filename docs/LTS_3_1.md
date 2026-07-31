# IT-Projektzentrale 3.1 LTS

Die 3.1-LTS-Reihe ist ausschließlich für Stabilität, Upgrade-Sicherheit, Diagnose und Wartbarkeit vorgesehen.

## Garantien

- keine neuen Produktfunktionen innerhalb der 3.1.x-Reihe
- bestehende Konfiguration und Datenbank bleiben bei Upgrades erhalten
- Hauptdienst startet vor Worker und Monitoring
- Release nur nach Runtime-Import, Tests und Debian-Paketbau
- fehlerhafte Installationen liefern eine klare Diagnose

## Betriebsprüfung

```bash
sudo -u it-projektzentrale env $(sudo grep -v '^#' /etc/it-projektzentrale.conf | xargs) \
  /usr/lib/it-projektzentrale/itpz-doctor
curl -fsS http://127.0.0.1:8000/health
systemctl --failed
```

## Wiederherstellung

Bei einem fehlgeschlagenen Upgrade werden Worker und Monitoring gestoppt. Die bestehende Datenbank und Konfiguration werden nicht gelöscht. Nach Korrektur kann die Paketkonfiguration mit `sudo dpkg --configure -a` erneut ausgeführt werden.
