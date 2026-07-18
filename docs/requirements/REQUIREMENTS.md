# Anforderungen – IT-Projektzentrale

## 1. Zweck

Die IT-Projektzentrale ist eine zentrale Weboberfläche zur Installation, Verwaltung, Aktualisierung und zum Aufruf eigener IT-Projekte.

## 2. Grundanforderungen

- Die Anwendung wird als Debian-Paket (DEB) bereitgestellt.
- Die Weboberfläche ist nach der Installation standardmäßig über HTTP-Port 80 erreichbar.
- Die Grundinstallation enthält keine vorinstallierten Projekte.
- Installierte Projekte werden zentral erfasst und verwaltet.
- Die Bedienung erfolgt über eine übersichtliche Weboberfläche.

## 3. Dashboard

- Das Dashboard zeigt alle installierten Projekte.
- Jedes installierte Projekt besitzt einen direkten Link zu seiner Weboberfläche.
- Zu jedem Projekt werden mindestens Name, Status, Version und Zieladresse angezeigt.
- Ist kein Projekt installiert, zeigt das Dashboard einen verständlichen Leerzustand.

## 4. Projektinstallation

- Projekte können über die Weboberfläche als DEB-Paket installiert werden.
- Als Installationsquellen werden lokale Uploads, GitHub und Gitea unterstützt.
- Zugangsdaten und Tokens für GitHub und Gitea werden geschützt gespeichert.
- Vor der Installation werden Paketname, Version und Quelle angezeigt.
- Fehler während der Installation werden verständlich protokolliert und ausgegeben.

## 5. Projektaktualisierung

- Für installierte Projekte kann über die Weboberfläche nach Aktualisierungen gesucht werden.
- Aktualisierungen können aus der jeweils konfigurierten GitHub- oder Gitea-Quelle installiert werden.
- Vor einer Aktualisierung werden aktuelle und verfügbare Version angezeigt.
- Fehlgeschlagene Aktualisierungen dürfen den bisherigen funktionsfähigen Stand nicht unkontrolliert beschädigen.

## 6. Projektentfernung

- Installierte Projekte können über die Weboberfläche deinstalliert werden.
- Vor der Deinstallation ist eine eindeutige Bestätigung erforderlich.
- Die Anwendung weist darauf hin, ob Konfigurationen und Projektdaten erhalten oder entfernt werden.
- Nach erfolgreicher Deinstallation wird das Projekt aus dem Dashboard entfernt.

## 7. Projektverwaltung

- Projekte können mit Name, Beschreibung, Version, Webadresse und Installationsquelle verwaltet werden.
- GitHub- und Gitea-Verbindungen können je Projekt konfiguriert werden.
- Status und Erreichbarkeit eines Projekts werden nachvollziehbar dargestellt.
- Aktionen und technische Meldungen werden protokolliert.

## 8. Sicherheit

- Verwaltungsfunktionen sind nur für berechtigte Benutzer zugänglich.
- Passwörter und Zugriffstokens werden nicht im Klartext in der Weboberfläche oder in Protokollen ausgegeben.
- Installations-, Update- und Deinstallationsaktionen werden serverseitig validiert.
- Hochgeladene Pakete werden vor der Verarbeitung geprüft.
- Systembefehle werden ausschließlich mit kontrollierten Parametern ausgeführt.

## 9. Qualität und Betrieb

- Die Anwendung ist für Debian-basierte Systeme vorgesehen.
- Installation, Aktualisierung und Deinstallation der IT-Projektzentrale selbst sind dokumentiert.
- Fehler werden mit Zeitstempel und ausreichendem technischem Kontext protokolliert.
- Die Oberfläche ist auf Desktop, Tablet und Smartphone nutzbar.
- Anforderungen werden bei der Weiterentwicklung in diesem Dokument gepflegt.

## 10. Offene Konkretisierungen

- Unterstützte Debian- und Raspberry-Pi-OS-Versionen
- Benutzer- und Rollenmodell
- Sicherungs- und Wiederherstellungsverfahren
- Verhalten bei Abhängigkeitskonflikten zwischen DEB-Paketen
- Definition der Schnittstelle beziehungsweise Metadaten für verwaltete Projekte
- Umfang der automatischen Erreichbarkeits- und Gesundheitsprüfungen
