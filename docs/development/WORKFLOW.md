# Entwicklungs- und Veröffentlichungsablauf

## 1. Anforderungen

- offene Frage gemeinsam entscheiden
- Entscheidung in `docs/requirements/DECISIONS.md` erfassen
- Lastenheft anpassen
- offene Frage als erledigt markieren

## 2. Technische Planung

- Pflichtenheft und Architekturentscheidung erstellen
- Auswirkungen auf Sicherheit, Daten, Migrationen und Paketierung prüfen
- Abnahmekriterien und Tests vor der Implementierung festlegen

## 3. Umsetzung

- kleine, modulare Änderung umsetzen
- serverseitige Berechtigungen und Fehlerbehandlung ergänzen
- automatisierte Tests schreiben
- Dokumentation aktualisieren

## 4. Prüfung

- Format-, Typ- und Sicherheitstests
- automatisierte Unit- und Integrationstests
- Paketbau und Installation auf unterstützten Testsystemen
- Update-, Backup-, Wiederherstellungs- und Deinstallationstests, soweit betroffen
- Prüfung, dass keine Geheimnisse eingecheckt wurden

## 5. Version und Veröffentlichung

- `version.txt`, Anwendung, Paketmetadaten und Dokumentation synchron aktualisieren
- `CHANGELOG.md` ergänzen
- vollständiges Debian-Paket bauen
- Prüfsummen erzeugen
- GitHub-Release mit verständlichen Installations- und Aktualisierungshinweisen veröffentlichen
- Release-Artefakte niemals nur im Chat oder in einer externen ZIP-Dokumentation verwalten

## Commit-Grundsätze

- ein klarer Zweck pro Commit
- verständliche deutsche oder etablierte technische Commit-Beschreibung
- keine generierten Laufzeitdaten oder Geheimnisse
- keine Behauptung „fertig“, wenn Tests oder Paket fehlen

