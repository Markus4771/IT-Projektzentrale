# Installation

## Aktueller Stand

`1.0.0-beta.1` ist als Debian-Paket vorhanden, aber wegen bekannter Sicherheitsblocker nur für ein abgeschottetes Testsystem vorgesehen. Nicht direkt auf einem öffentlich erreichbaren oder produktiven Server installieren.

## Lokale Testinstallation

Nach dem geprüften Download:

```bash
echo "6de66c1180931e1a34cbd79e4401a21153b17bde21e6efb6dc06d17423efbcdd  it-projektzentrale_1.0.0-beta.1_all.deb" | sha256sum -c -
sudo apt install ./it-projektzentrale_1.0.0-beta.1_all.deb
```

Anschließend ist die Anwendung grundsätzlich unter `http://<SERVER-IP>/` vorgesehen.

## Späterer öffentlicher Installationsweg

Produktiv freigegebene Pakete sollen als GitHub-Release mit SHA-256-Prüfsumme veröffentlicht werden:

```bash
wget https://github.com/Markus4771/IT-Projektzentrale/releases/download/v<VERSION>/it-projektzentrale_<VERSION>_<ARCHITEKTUR>.deb
wget https://github.com/Markus4771/IT-Projektzentrale/releases/download/v<VERSION>/SHA256SUMS
sha256sum -c SHA256SUMS
sudo apt install ./it-projektzentrale_<VERSION>_<ARCHITEKTUR>.deb
```

Ein Repository-Upload im Branch `main` ersetzt kein geprüftes GitHub-Release.

## Deinstallation

```bash
sudo apt remove it-projektzentrale
```

Eine vollständige Entfernung einschließlich Konfiguration und Daten muss vor Version 1.0 separat geprüft und dokumentiert werden.

