# Roadmap – IT-Projektzentrale

## Phase 0 – Konsolidierung der Beta 1

- [x] ursprüngliches DEB und ZIP sichern
- [x] Quellcode aus dem ZIP als Repository-Struktur übernehmen
- [x] Debian-Paketquellen rekonstruieren
- [x] Sicherheits- und Bestandsprüfung dokumentieren
- [ ] offene Lastenheftfragen entscheiden

## Phase 1 – Beta 2: Sicherheitsgrundlage

- [x] Initialkennwort und erzwungenen Passwortwechsel sicher umsetzen
- [ ] Benutzer und Rollen serverseitig umsetzen
- [x] CSRF-Schutz und Anmeldebegrenzung ergänzen
- [x] privilegierten Paket- und Diensthelfer mit Positivlisten einführen
- [ ] Geheimnisse geschützt speichern
- [x] API-Zugriff absichern
- [x] Eingaben, URLs und Uploadgrößen grundlegend validieren
- [x] automatisierte Sicherheits- und Integrationstests ergänzen

## Phase 2 – Lastenheft vollständig umsetzen

- [ ] Paket-, Architektur-, Konflikt- und Speicherplatzprüfung
- [ ] Installationsfortschritt und verlässliches Auftragsmodell
- [ ] Update-Sicherung und Rollback
- [ ] vollständige Backup-Wiederherstellung
- [ ] Projektmanifest und Gesundheitsprüfungen
- [ ] Benutzerfreigaben und Projektverwalter

## Phase 3 – Release 1.0

- [ ] Lasten- und Pflichtenheft freigeben
- [ ] unterstützte Debian- und CPU-Plattformen testen
- [ ] Abnahme-, Update-, Wiederherstellungs- und Deinstallationstests
- [ ] Sicherheitsfreigabe
- [ ] GitHub-Release mit DEB, ZIP, Prüfsummen und Installationsanleitung
