# Projekt-Retrospektive und Übergabeprotokoll

## Erreicht

- Beta-1-Artefakte und tatsächlichen Quellstand in GitHub gesichert
- reproduzierbaren DEB-Bau und automatisierte CI-Prüfungen eingerichtet
- zufälligen Erstzugang, erzwungenen Passwortwechsel, scrypt und Anmeldebegrenzung umgesetzt
- sitzungsgebundenen CSRF-Schutz und Anmeldungspflicht für Oberfläche und APIs ergänzt
- breite Systemrechte durch einen validierenden Root-Helfer mit root-eigenen Positivlisten ersetzt
- Programm-, Konfigurations- und Zustandsdaten sauber getrennt
- Upload-, URL-, Paketmetadaten- und Architekturprüfung ergänzt
- systemd, Nginx und Browserausführung gehärtet
- Sicherheitsstatus, Installation, Architektur und verbleibende Freigabepunkte dokumentiert

## Erkenntnisse

- Ein vorhandenes DEB ist nicht automatisch produktionsreif.
- Quellcode, Paketbau, Tests und Dokumentation müssen gemeinsam versioniert werden.
- Bekannte Standardzugänge und breite sudo-Regeln sind für eine öffentliche Installation nicht vertretbar.
- Eine enge Root-Schnittstelle begrenzt Befehle, macht untrusted Debian-Pakete aber nicht sicher.
- Lastenheft, tatsächlicher Code und veröffentlichte Funktionsaussagen müssen klar getrennt werden.

## Übergabepunkt

Beta 2 stellt die gehärtete Sicherheitsgrundlage her und bleibt eine Testversion. Die nächsten Schwerpunkte sind das vollständige Drei-Rollen-Modell, geschützte Tokenablage, Installationsaufträge mit Vorprüfung und Rollback sowie Wiederherstellungstests.
