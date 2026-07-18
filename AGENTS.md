# Arbeitsregeln für KI-Agenten und Entwickler

Diese Regeln gelten für das gesamte Repository.

## Vor jeder Bearbeitung lesen

1. `NEUER_CHAT.md`
2. `CHATGPT_PROJEKTKONTEXT.md`
3. `version.txt`
4. `README.md`
5. `docs/requirements/REQUIREMENTS.md`
6. `docs/requirements/OPEN_QUESTIONS.md`
7. `docs/requirements/DECISIONS.md`
8. `docs/security/SECURITY_REVIEW_1.0.0-beta.1.md`
9. `CHANGELOG.md`
10. anschließend den tatsächlichen Quellcode und die Debian-Paketierung

## Verbindliche Regeln

- Ausschließlich auf Basis des aktuellen GitHub-Stands arbeiten.
- Dokumentierte Anforderungen nicht als bereits implementierte Funktionen darstellen.
- Beta 1 ist ein vorhandener Teststand; neue Funktionen müssen trotzdem mit Lastenheft und Architektur abgestimmt werden.
- Bestehende Anforderungen und Funktionen nicht unbeabsichtigt verschlechtern.
- Änderungen modular und nachvollziehbar umsetzen.
- Berechtigungen immer serverseitig prüfen.
- Systembefehle niemals aus frei zusammengesetzten Benutzereingaben erzeugen.
- Geheimnisse niemals in GitHub, Quellcode, URLs, Protokolle oder Fehlermeldungen schreiben.
- Datenbankänderungen später ausschließlich über versionierte Migrationen durchführen.
- Jede Funktionsänderung benötigt passende Tests, Dokumentation und einen Eintrag in `CHANGELOG.md`.
- Versionsangaben in `version.txt`, Paketmetadaten, Anwendung, Dokumentation und Releases konsistent halten.
- Die Grundinstallation darf keine Beispielprojekte enthalten.
- Standard-Port 80, Paketname und Dienstname nur nach dokumentierter Entscheidung ändern.
- Beta 1 nicht als produktionsreif oder sicher zur öffentlichen Installation bezeichnen.

## Abschluss einer Aufgabe

Vor einem Commit sind mindestens zu prüfen:

- Was war gefordert?
- Was wurde tatsächlich geändert?
- Welche Tests wurden ausgeführt?
- Welche offenen Punkte bleiben?
- Müssen Lastenheft, Projektkontext, Roadmap, Changelog oder Versionsdatei aktualisiert werden?
