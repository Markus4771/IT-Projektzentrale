# Projekt-Retrospektive und Übergabeprotokoll

## Erreicht

- ursprüngliche Empfangswebseite zur Projektzentrale konkretisiert
- Lastenheft mit Dashboard, Projekten, DEB, GitHub, Gitea, Updates, Backups, Diensten und Rollen erstellt
- Beta 1 mit Quellcode, ZIP und Debian-Paket erzeugt
- leere Grundinstallation und Port 80 umgesetzt
- Beta-1-Dateien nach GitHub übertragen
- Quellcode und Paketinhalt miteinander verglichen
- Sicherheits- und Freigabeblocker identifiziert
- Repository für reproduzierbare Weiterentwicklung vorbereitet

## Erkenntnisse

- Ein vorhandenes DEB ist nicht automatisch produktionsreif.
- Chat-Downloads werden nicht automatisch nach GitHub übertragen.
- Quellcode muss sichtbar und Paketbau reproduzierbar im Repository liegen.
- Bekannte Standardzugänge und breite sudo-Regeln sind für eine öffentliche Installation nicht vertretbar.
- Lastenheft, tatsächlicher Code und veröffentlichte Funktionsaussagen müssen klar getrennt werden.

## Übergabepunkt

Die Beta 1 ist vollständig gesichert und analysiert. Als Nächstes werden die Sicherheitsblocker behoben und anschließend eine Beta 2 gebaut und getestet.

