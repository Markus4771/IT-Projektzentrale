# Installation

## Aktueller Stand

`1.0.0-beta.2` ist ein gehärteter Teststand. Zuerst auf einem abgeschotteten Debian-Testsystem prüfen; eine Produktivfreigabe besteht noch nicht.

## Paket aus dem Quellcode bauen

```bash
git clone https://github.com/Markus4771/IT-Projektzentrale.git
cd IT-Projektzentrale
bash scripts/build_deb.sh
sha256sum -c dist/it-projektzentrale_1.0.0-beta.2_all.deb.sha256
sudo apt install ./dist/it-projektzentrale_1.0.0-beta.2_all.deb
```

Alternativ führt `sudo bash install.sh` Paketbau, Prüfsummenprüfung und Installation aus.

Nach der Installation:

```bash
sudo cat /root/it-projektzentrale-initial-password
```

Anschließend `http://<SERVER-IP>/` öffnen, mit dem angezeigten Initialzugang anmelden und sofort ein eigenes Passwort mit mindestens 12 Zeichen festlegen.

Nach erfolgreichem Passwortwechsel kann die dann ungültige Übergabedatei entfernt werden:

```bash
sudo rm /root/it-projektzentrale-initial-password
```

Port 80 ist für ein abgeschottetes Testnetz vorgesehen. Vor einem Betrieb über öffentliche oder nicht vertrauenswürdige Netze muss HTTPS eingerichtet und `ITPZ_HTTPS_ONLY=1` in `/etc/it-projektzentrale.conf` gesetzt werden.

## Upgrade von Beta 1

Die Beta 2 übernimmt vorhandene Projekt- und Paketdaten aus `/opt/it-projektzentrale` nach `/var/lib/it-projektzentrale`. Der unsichere Beta-1-Initialzugang `admin/admin` wird durch einen zufälligen Initialzugang ersetzt, wenn noch kein sicherer Benutzerbestand vorhanden ist.

Vor dem Upgrade ein Systembackup erstellen und die Migration zunächst auf einem Testsystem prüfen.

Installiere ausschließlich selbst gebaute oder anderweitig vertrauenswürdig bezogene Debian-Pakete. Ein DEB kann während der Installation Code mit Root-Rechten ausführen.

## Späterer öffentlicher Release-Weg

Freigegebene Pakete sollen als GitHub-Release mit Prüfsumme veröffentlicht werden:

```bash
wget https://github.com/Markus4771/IT-Projektzentrale/releases/download/v<VERSION>/it-projektzentrale_<VERSION>_<ARCHITEKTUR>.deb
wget https://github.com/Markus4771/IT-Projektzentrale/releases/download/v<VERSION>/SHA256SUMS
sha256sum -c SHA256SUMS
sudo apt install ./it-projektzentrale_<VERSION>_<ARCHITEKTUR>.deb
```

## Deinstallation

```bash
sudo apt remove it-projektzentrale
```

Konfiguration und Daten bleiben bei `remove` erhalten. Eine vollständige Entfernung erfolgt erst nach geprüftem Backup über `sudo apt purge it-projektzentrale`.
