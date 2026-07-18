# Lastenheft – IT-Projektzentrale

| Merkmal | Stand |
|---|---|
| Projekt | IT-Projektzentrale |
| Dokumenttyp | Lastenheft / Anforderungsdefinition |
| Dokumentstatus | Entwurf |
| Stand | 18. Juli 2026 |
| Repository | Markus4771/IT-Projektzentrale |
| Zielversion | Version 1.0 |

## 1. Zweck des Dokuments

Dieses Lastenheft beschreibt, **was** die IT-Projektzentrale leisten soll. Technische Einzelheiten der Umsetzung werden anschließend in einem Pflichtenheft festgelegt.

Für Anforderungen gelten folgende Begriffe:

- **MUSS:** für Version 1.0 zwingend erforderlich
- **SOLL:** für Version 1.0 vorgesehen, sofern kein begründetes Hindernis besteht
- **KANN:** mögliche spätere Erweiterung

## 2. Ausgangssituation

Mehrere eigenständige IT-Projekte werden auf Debian-basierten Systemen betrieben. Die Projekte besitzen eigene Weboberflächen, Installationspakete, Dienste, Versionen und teilweise eigene GitHub- oder Gitea-Repositories.

Ohne eine zentrale Oberfläche müssen Adressen, Versionsstände, Installationen, Aktualisierungen und technische Informationen getrennt verwaltet werden. Die IT-Projektzentrale soll diese Aufgaben in einer gemeinsamen Weboberfläche bündeln.

## 3. Produktziel

Die IT-Projektzentrale wird zur zentralen Empfangs-, Installations- und Verwaltungsoberfläche für eigene IT-Projekte.

Die Anwendung MUSS:

- installierte Projekte übersichtlich anzeigen,
- direkte Aufrufe der jeweiligen Projekt-Weboberflächen ermöglichen,
- Projekte aus DEB-Paketen installieren,
- GitHub und Gitea als Installations- und Aktualisierungsquellen unterstützen,
- Aktualisierungen verwalten,
- Projekte kontrolliert deinstallieren,
- Benutzerrechte berücksichtigen,
- Sicherungs-, Dienst- und Dokumentationsfunktionen bereitstellen,
- selbst als Debian-Paket installierbar sein,
- nach der Grundinstallation ohne vorinstallierte Projekte starten.

## 4. Abgrenzung der Version 1.0

Version 1.0 konzentriert sich auf die zuverlässige Verwaltung von Projekten auf dem System, auf dem die IT-Projektzentrale installiert ist.

### 4.1 Umfang von Version 1.0

Die Hauptnavigation umfasst:

1. Dashboard
2. Projekte
3. Installation
4. Updates
5. Backups
6. Dienste
7. Dokumentation
8. News
9. Benutzer
10. Einstellungen

### 4.2 Nicht als eigene Hauptmenüs für Version 1.0 vorgesehen

Folgende Bereiche bleiben für spätere Versionen im Backlog:

- Downloads
- Suche
- Statistiken
- separate Rollenverwaltung
- separates Log-Menü
- Entwicklerbereich
- Supportbereich
- öffentliche API

Rollen und Protokolle werden in Version 1.0 innerhalb der Benutzerverwaltung beziehungsweise der Einstellungen abgebildet.

## 5. Benutzer- und Rollenmodell

Die Anwendung MUSS mehrere Benutzer unterstützen. Es gelten drei Rollen:

### 5.1 Administrator

Administratoren besitzen vollständige Kontrolle über die IT-Projektzentrale. Sie dürfen insbesondere:

- alle Projekte sehen und verwalten,
- Projekte anlegen, installieren, aktualisieren und löschen,
- Projekte Benutzern und Projektverwaltern zuweisen,
- Benutzerkonten anlegen, ändern, deaktivieren und löschen,
- Rollen vergeben,
- globale GitHub-, Gitea-, Sicherheits-, Backup- und Systemeinstellungen verwalten,
- alle Protokolle einsehen,
- Dienste und die IT-Projektzentrale selbst verwalten.

### 5.2 Projektverwalter

Projektverwalter dürfen ausschließlich die ihnen durch einen Administrator zugewiesenen Projekte verwalten. Innerhalb dieser Zuweisung dürfen sie:

- Projektinformationen bearbeiten,
- Projekte installieren,
- Projekte aktualisieren,
- Projekte löschen,
- den Status und die Protokolle der zugewiesenen Projekte einsehen,
- projektbezogene Dienste bedienen.

Projektverwalter dürfen keine Benutzer, Rollen oder globalen Sicherheitseinstellungen verwalten.

### 5.3 Benutzer mit Lesezugriff

Benutzer mit Lesezugriff sehen ausschließlich die Projekte, die ein Administrator für sie freigegeben hat. Sie dürfen:

- freigegebene Projektkacheln im Dashboard sehen,
- freigegebene Projektinformationen lesen,
- die Weboberfläche eines freigegebenen Projekts über den Schnellzugriff öffnen,
- freigegebene Dokumentation und News lesen.

Sie dürfen keine Projekte, Dienste oder Einstellungen verändern. Nicht freigegebene Projekte werden vollständig ausgeblendet.

### 5.4 Berechtigungsübersicht

| Funktion | Administrator | Projektverwalter | Lesezugriff |
|---|---:|---:|---:|
| Freigegebene Projekte anzeigen | Ja | Ja | Ja |
| Alle Projekte anzeigen | Ja | Nein | Nein |
| Projekt-Weboberfläche öffnen | Ja | Zugewiesen/freigegeben | Freigegeben |
| Projektinformationen bearbeiten | Ja | Zugewiesen | Nein |
| Projekt installieren | Ja | Zugewiesen | Nein |
| Projekt aktualisieren | Ja | Zugewiesen | Nein |
| Projekt löschen | Ja | Zugewiesen | Nein |
| Projektbezogene Dienste bedienen | Ja | Zugewiesen | Nein |
| Benutzer und Rollen verwalten | Ja | Nein | Nein |
| Globale Einstellungen verwalten | Ja | Nein | Nein |
| Globale Backups wiederherstellen | Ja | Nein | Nein |

Berechtigungen MÜSSEN serverseitig geprüft werden. Das bloße Ausblenden einer Schaltfläche reicht nicht aus.

## 6. Benutzerkonten und erste Anmeldung

- Benutzerkonten werden ausschließlich durch Administratoren angelegt, geändert, deaktiviert oder gelöscht.
- Eine öffentliche Selbstregistrierung ist nicht vorgesehen.
- Bei der DEB-Installation wird ein festes Standard-Administratorkonto mit festem Initialpasswort angelegt.
- Beim ersten Login MUSS das Initialpasswort zwingend geändert werden.
- Bis zum erfolgreichen Passwortwechsel bleiben alle anderen Funktionen gesperrt.
- Nach dem Passwortwechsel ist das Initialpasswort für dieses Konto ungültig.
- Passwörter dürfen ausschließlich sicher gehasht gespeichert werden.
- Das konkrete Standardkonto und Initialpasswort werden vor Freigabe des Lastenhefts festgelegt.

## 7. Bedien- und Menükonzept

Die Weboberfläche MUSS übersichtlich, deutschsprachig und auf Desktop, Tablet und Smartphone bedienbar sein. Menüs und Aktionen werden abhängig von der Rolle und den Projektfreigaben angezeigt.

### 7.1 Dashboard

Das Dashboard ist die Startseite nach der Anmeldung.

Es MUSS:

- jedes sichtbare installierte Projekt als eigene Kachel darstellen,
- mindestens Name, Beschreibung, installierte Version, Status und Zieladresse anzeigen,
- einen deutlich erkennbaren Schnellzugriff zur Projekt-Weboberfläche anbieten,
- verfügbare Aktualisierungen kennzeichnen,
- nicht erreichbare Projekte verständlich markieren,
- die Sichtbarkeitsregeln des Rollenmodells beachten,
- bei einer leeren Grundinstallation einen verständlichen Leerzustand anzeigen.

Auf dem leeren Dashboard wird darauf hingewiesen, dass noch keine Projekte installiert sind. Berechtigte Benutzer erhalten einen direkten Weg zum Installationsbereich.

### 7.2 Projekte

Der Bereich „Projekte“ dient der Übersicht und Pflege aller für den angemeldeten Benutzer sichtbaren Projekte.

Eine Projektansicht MUSS mindestens enthalten:

- Projektname
- Kurzbeschreibung
- ausführliche Beschreibung
- installierte Version
- Paketname
- Installationsstatus
- Webadresse
- Installationsquelle
- Repository beziehungsweise Release-Quelle
- zugehöriger Systemdienst, sofern vorhanden
- Erreichbarkeitsstatus
- Datum der letzten Installation oder Aktualisierung
- zugewiesene Projektverwalter
- freigeschaltete Benutzer
- verfügbare Aktionen entsprechend der Benutzerrolle

### 7.3 Installation

Der Installationsbereich MUSS drei Quellen unterstützen:

1. lokaler DEB-Upload
2. GitHub
3. Gitea

Vor einer Installation MUSS die Anwendung mindestens Quelle, Paketname, Version, Architektur und erkannte Abhängigkeiten anzeigen. Die Installation beginnt erst nach einer ausdrücklichen Bestätigung.

### 7.4 Updates

Der Updatebereich zeigt:

- installierte Projekte,
- aktuell installierte Versionen,
- konfigurierte Updatequellen,
- verfügbare Versionen,
- Datum der letzten Prüfung,
- Ergebnis der letzten Aktualisierung.

Aktualisierungen werden in Version 1.0 bewusst durch einen berechtigten Benutzer gestartet. Vollautomatische Aktualisierungen gehören nicht zum verpflichtenden Umfang.

### 7.5 Backups

Der Backupbereich SOLL mindestens die Konfiguration und Daten der IT-Projektzentrale sichern und wiederherstellen können. Dazu gehören insbesondere:

- Projektmetadaten
- Benutzer, Rollen und Freigaben
- Quell- und Verbindungskonfigurationen ohne ungeschützte Ausgabe von Geheimnissen
- Einstellungen
- Protokoll- und Versionsinformationen, soweit für eine Wiederherstellung erforderlich

Die Sicherung der Anwendungsdaten einzelner verwalteter Projekte ist nur Bestandteil, wenn das jeweilige Projekt dafür eine definierte Schnittstelle bereitstellt.

### 7.6 Dienste

Der Dienstebereich zeigt die der IT-Projektzentrale und den verwalteten Projekten zugeordneten Systemdienste.

Berechtigte Benutzer SOLLEN:

- Dienststatus sehen,
- Startzeit und letzten Fehler sehen,
- zugeordnete Dienste starten, stoppen und neu starten können,
- vor unterbrechenden Aktionen eine Bestätigung erhalten.

Projektverwalter dürfen ausschließlich Dienste ihrer zugewiesenen Projekte bedienen.

### 7.7 Dokumentation

Der Dokumentationsbereich stellt zentrale Informationen bereit, darunter:

- Installationsanleitung
- Bedienungsanleitung
- Administratorhandbuch
- Hinweise zu GitHub und Gitea
- projektspezifische Dokumentation, sofern hinterlegt
- Hilfe zu Fehlern, Updates und Wiederherstellung

### 7.8 News

Der Newsbereich zeigt zentrale Hinweise, Versionsinformationen und projektbezogene Meldungen. Die genaue Quelle und Pflege der Meldungen wird noch festgelegt.

### 7.9 Benutzer

Der Benutzerbereich ist nur für Administratoren sichtbar. Er umfasst:

- Benutzer anlegen und bearbeiten
- Konto aktivieren oder deaktivieren
- Rolle vergeben
- Projekte zuweisen oder freigeben
- Passwort zurücksetzen
- erzwungenen Passwortwechsel auslösen
- letzte Anmeldung und Kontostatus anzeigen

### 7.10 Einstellungen

Die Einstellungen umfassen mindestens:

- allgemeine Angaben zur IT-Projektzentrale
- GitHub-Verbindungen
- Gitea-Verbindungen
- Zugangstokens und Anmeldedaten
- Backup-Einstellungen
- Sicherheits- und Sitzungseinstellungen
- System- und Dienstinformationen
- Protokolle
- Aktualisierung der IT-Projektzentrale selbst

## 8. Projektverwaltung

### PRJ-001 – Leere Grundinstallation

Die Grundinstallation MUSS ohne vorinstallierte Projekte ausgeliefert werden. Beispiel-, Demo- oder fest einprogrammierte Projekte sind nicht zulässig.

### PRJ-002 – Projekt anlegen

Ein Administrator MUSS einen neuen Projekteintrag anlegen können. Ob Projektverwalter selbst neue Projekteinträge anlegen dürfen, bleibt noch festzulegen.

### PRJ-003 – Projekt bearbeiten

Berechtigte Benutzer MÜSSEN Name, Beschreibung, Webadresse, Paketdaten, Quelle, Dienst und Freigaben eines Projekts bearbeiten können.

### PRJ-004 – Dashboard-Schnellzugriff

Nach erfolgreicher Installation MUSS das Projekt automatisch im Dashboard erscheinen. Die Projektkachel MUSS direkt zur hinterlegten Weboberfläche führen.

### PRJ-005 – Erreichbarkeit

Die IT-Projektzentrale SOLL die konfigurierte Webadresse eines Projekts prüfen und einen verständlichen Status anzeigen. Eine Nichterreichbarkeit darf den Aufruf oder andere Projekte nicht blockieren.

## 9. Installation von Projekten

### INS-001 – Lokaler DEB-Upload

Berechtigte Benutzer MÜSSEN ein DEB-Paket über die Weboberfläche hochladen und installieren können.

### INS-002 – GitHub als Quelle

Die Anwendung MUSS öffentliche und private GitHub-Repositories als Projektquelle unterstützen. Bei privaten Repositories wird ein sicher gespeicherter Token verwendet.

Die Anwendung SOLL:

- Releases abrufen,
- geeignete DEB-Dateien eines Releases anzeigen,
- Version und Architektur erkennen,
- eine ausgewählte Release-Datei installieren,
- die Quelle für spätere Updates speichern.

### INS-003 – Gitea als Quelle

Die Anwendung MUSS Gitea-Repositories entsprechend dem GitHub-Ablauf unterstützen. Serveradresse, Repository und Zugangstoken müssen konfigurierbar sein.

### INS-004 – Verbindungsprüfung

GitHub- und Gitea-Verbindungen MÜSSEN vor der Nutzung getestet werden können. Fehler werden ohne Offenlegung von Tokens verständlich angezeigt.

### INS-005 – Paketprüfung

Vor der Installation MUSS das Paket geprüft werden. Mindestens folgende Informationen sind zu erfassen:

- gültiges Debian-Paket
- Paketname
- Version
- Zielarchitektur
- Abhängigkeiten
- Installationsquelle

Nicht unterstützte oder offensichtlich ungültige Pakete dürfen nicht installiert werden.

### INS-006 – Bestätigung und Fortschritt

Die Installation MUSS ausdrücklich bestätigt werden. Während der Installation werden Status und verständliche Fortschrittsmeldungen angezeigt.

### INS-007 – Ergebnis und Protokoll

Nach Abschluss MUSS eindeutig angezeigt werden, ob die Installation erfolgreich war. Fehlerausgaben werden protokolliert, dürfen aber keine Passwörter oder Tokens enthalten.

## 10. Aktualisierung von Projekten

### UPD-001 – Updateprüfung

Für jedes Projekt MUSS anhand der gespeicherten Quelle geprüft werden können, ob eine neuere Version verfügbar ist.

### UPD-002 – Versionsvergleich

Vor einer Aktualisierung werden installierte und verfügbare Version gegenübergestellt.

### UPD-003 – Manuelle Freigabe

Eine Aktualisierung beginnt erst nach Auswahl und Bestätigung durch einen berechtigten Benutzer.

### UPD-004 – Schutz bestehender Daten

Konfigurationen und Nutzdaten eines Projekts dürfen durch eine reguläre Aktualisierung nicht unbeabsichtigt gelöscht werden.

### UPD-005 – Fehlerbehandlung

Eine fehlgeschlagene Aktualisierung darf den bisherigen funktionsfähigen Stand nicht unkontrolliert beschädigen. Das konkrete Sicherungs- und Rücksetzverfahren wird im Pflichtenheft festgelegt.

### UPD-006 – Aktualisierung der Projektzentrale

Die IT-Projektzentrale SOLL ihre eigene installierte Version und verfügbare Aktualisierungen anzeigen. Nur Administratoren dürfen die Aktualisierung der Projektzentrale starten.

## 11. Deinstallation von Projekten

### DEL-001 – Berechtigung

Administratoren dürfen alle Projekte löschen. Projektverwalter dürfen ausschließlich zugewiesene Projekte löschen.

### DEL-002 – Eindeutige Bestätigung

Vor einer Deinstallation MUSS eine eindeutige Bestätigung mit Projektname und Paketname erfolgen.

### DEL-003 – Datenbehandlung

Vor der Deinstallation MUSS angezeigt werden, ob Konfigurationen und Projektdaten erhalten oder entfernt werden. Die endgültige technische Trennung zwischen Paket, Konfiguration und Nutzdaten wird noch festgelegt.

### DEL-004 – Abschluss

Nach erfolgreicher Deinstallation wird das Projekt aus Dashboard, Projektliste, Updateübersicht und Dienstzuordnung entfernt.

### DEL-005 – Protokollierung

Die Deinstallation und ihr Ergebnis werden mit Benutzer, Zeitpunkt, Projekt und Ergebnis protokolliert.

## 12. GitHub- und Gitea-Integration

- Mehrere GitHub- und Gitea-Verbindungen MÜSSEN verwaltet werden können.
- Eine Quelle MUSS pro Projekt auswählbar sein.
- Öffentliche und private Repositories MÜSSEN unterstützt werden.
- Tokens und Kennwörter dürfen weder vollständig angezeigt noch protokolliert werden.
- Verbindungen MÜSSEN getestet, geändert und deaktiviert werden können.
- Beim Wechsel einer Quelle muss eine Warnung erscheinen, wenn dadurch der Updatepfad des Projekts verändert wird.
- Release-Dateien MÜSSEN nach DEB-Paketen und geeigneter Architektur gefiltert werden können.

## 13. Backup und Wiederherstellung

- Backups MÜSSEN manuell erstellt werden können.
- Vor einer Wiederherstellung MUSS eine Bestätigung erfolgen.
- Ein Backup MUSS auf Vollständigkeit und Lesbarkeit geprüft werden.
- Eine Wiederherstellung MUSS protokolliert werden.
- Zugangsdaten dürfen in exportierten Sicherungen nicht ungeschützt vorliegen.
- Speicherziele, Zeitpläne, Aufbewahrung und Umfang werden noch konkretisiert.

## 14. Sicherheit

Die Anwendung MUSS mindestens folgende Sicherheitsanforderungen erfüllen:

- serverseitige Rollen- und Rechteprüfung
- Schutz vor unberechtigtem Zugriff auf Verwaltungsfunktionen
- sichere Passwort-Hashes
- sichere Sitzungscookies
- Schutz vor CSRF bei verändernden Webaktionen
- Validierung sämtlicher Benutzereingaben
- kontrollierte Ausführung notwendiger Systembefehle ohne frei zusammengesetzte Shell-Befehle
- Prüfung hochgeladener Dateien
- restriktive Dateirechte für Tokens und Konfigurationen
- keine Geheimnisse in Oberfläche, URL, Protokollen oder Fehlermeldungen
- nachvollziehbare Protokollierung sicherheitsrelevanter Aktionen
- verpflichtender Wechsel des Initialpassworts

Die Anwendung ist nicht als Ersatz für die eigene Anmeldung oder Rechteverwaltung der verwalteten Projekte gedacht. Der Schnellzugriff öffnet die jeweilige Projekt-Weboberfläche; deren Anmeldung bleibt eigenständig.

## 15. Protokollierung und Nachvollziehbarkeit

Mindestens folgende Aktionen MÜSSEN protokolliert werden:

- erfolgreiche und fehlgeschlagene Anmeldung
- Passwortwechsel und administratives Zurücksetzen
- Benutzer- und Rollenänderungen
- Projektanlage und Projektänderung
- Installation
- Updateprüfung und Aktualisierung
- Deinstallation
- Dienstaktionen
- Backup und Wiederherstellung
- Änderungen an GitHub- und Gitea-Verbindungen
- Änderungen an sicherheitsrelevanten Einstellungen

Ein Eintrag enthält mindestens Zeitpunkt, Benutzer, Aktion, betroffenes Objekt und Ergebnis.

## 16. Technische und betriebliche Rahmenbedingungen

- Das Produkt wird als Debian-Paket mit dem Paketnamen **it-projektzentrale** bereitgestellt.
- Der vorgesehene Dienstname lautet **it-projektzentrale**.
- Die Weboberfläche MUSS standardmäßig über HTTP-Port 80 erreichbar sein.
- Zielsysteme sind Debian-basierte Linux-Systeme.
- Die konkrete Liste unterstützter Distributionen und Architekturen wird noch festgelegt.
- Die Grundinstallation MUSS alle für die Projektzentrale benötigten Abhängigkeiten nachvollziehbar einrichten.
- Installation, Update und Deinstallation des Produkts MÜSSEN dokumentiert werden.
- Die geplante technische Basis aus FastAPI, Nginx und einem Systemdienst wird im Pflichtenheft abschließend beschrieben.
- Konfigurationen und veränderliche Daten müssen von Programmdateien getrennt behandelt werden.
- Ein Neustart des Servers darf nicht dazu führen, dass die Projektzentrale oder ihre registrierten Projekte aus der Übersicht verschwinden.

## 17. Qualitätsanforderungen

### 17.1 Bedienbarkeit

- durchgehend verständliche deutsche Bezeichnungen
- konsistente Navigation und Schaltflächen
- Bestätigungen bei riskanten Aktionen
- verständliche Fehler- und Erfolgsmeldungen
- responsives Layout für Desktop, Tablet und Smartphone
- sichtbare Lade- und Fortschrittszustände bei längeren Aktionen

### 17.2 Zuverlässigkeit

- Fehler eines einzelnen Projekts dürfen die Projektzentrale nicht unbenutzbar machen.
- Unterbrochene Installationen und Aktualisierungen müssen erkennbar sein.
- Datenbank- und Konfigurationsänderungen müssen konsistent durchgeführt werden.
- Nach einem Neustart muss der letzte bestätigte Zustand wieder verfügbar sein.

### 17.3 Wartbarkeit

- Anforderungen, Installation und Bedienung werden im Repository dokumentiert.
- Erweiterungen dürfen bestehende Projektdefinitionen nicht ohne Migration unbrauchbar machen.
- Versionsänderungen und relevante Funktionsänderungen werden nachvollziehbar dokumentiert.

## 18. Abnahmekriterien für Version 1.0

Version 1.0 gilt aus Sicht des Lastenhefts als abnahmefähig, wenn mindestens folgende Prüfungen erfolgreich sind:

1. Das DEB-Paket lässt sich auf einem unterstützten Zielsystem installieren.
2. Die Weboberfläche ist anschließend über Port 80 erreichbar.
3. Das feste Administratorkonto verlangt beim ersten Login zwingend einen Passwortwechsel.
4. Die Grundinstallation zeigt keine vorinstallierten Projekte.
5. Ein gültiges DEB-Paket kann über die Weboberfläche installiert werden.
6. Ein Projekt kann aus einem GitHub-Release installiert werden.
7. Ein Projekt kann aus einem Gitea-Release installiert werden.
8. Ein installiertes Projekt erscheint mit funktionierendem Schnellzugriff im Dashboard.
9. Eine verfügbare Aktualisierung wird erkannt und kann bestätigt installiert werden.
10. Ein zugewiesener Projektverwalter kann sein Projekt installieren, aktualisieren und löschen.
11. Derselbe Projektverwalter kann keine nicht zugewiesenen Projekte verwalten.
12. Ein Benutzer mit Lesezugriff sieht nur freigegebene Projekte und kann keine Änderungen durchführen.
13. Eine bestätigte Deinstallation entfernt das Projekt aus den zugehörigen Übersichten.
14. Ein Backup der Projektzentrale kann erstellt und geprüft wiederhergestellt werden.
15. Aktionen und Fehler werden ohne Offenlegung von Zugangsdaten protokolliert.

## 19. Offene Punkte

Folgende Punkte werden im weiteren Lastenheft gemeinsam konkretisiert:

1. konkreter Benutzername und konkretes Initialpasswort des Standard-Administratorkontos
2. unterstützte Debian-, Raspberry-Pi-OS- und Architekturversionen
3. ob Projektverwalter neue Projekteinträge selbst anlegen dürfen
4. genaue Sichtbarkeit nicht zugewiesener, aber eventuell freigegebener Projekte für Projektverwalter
5. Speicherziele, Zeitpläne und Aufbewahrung von Backups
6. Umfang der Sicherung von Daten einzelner verwalteter Projekte
7. Verhalten bei Abhängigkeits- und Paketkonflikten
8. verbindliche Projektmetadaten beziehungsweise eine Projektschnittstelle
9. Art und Intervall der Erreichbarkeits- und Gesundheitsprüfungen
10. Rücksetzverfahren nach einer fehlgeschlagenen Aktualisierung
11. Behandlung von Projektkonfiguration und Nutzdaten bei Deinstallation
12. Quelle und Pflege der News
13. ob es zusätzlich eine öffentliche Ansicht ohne Anmeldung geben soll

## 20. Weiteres Vorgehen

Nach inhaltlicher Prüfung und Freigabe dieses Lastenhefts folgen:

1. Abschluss der offenen Anforderungen
2. Priorisierung in MUSS, SOLL und KANN
3. formelle Freigabe des Lastenhefts
4. Erstellung des technischen Pflichtenhefts
5. Architektur- und Datenmodell
6. Umsetzungsplanung in nachvollziehbaren Entwicklungsphasen
7. Beginn der Entwicklung
