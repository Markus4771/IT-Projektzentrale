# Anforderungen – IT-Projektzentrale

## 1. Zweck

Die IT-Projektzentrale ist eine zentrale Weboberfläche zur Installation, Verwaltung, Aktualisierung und zum Aufruf eigener IT-Projekte.

## 2. Grundanforderungen

- Die Anwendung wird als Debian-Paket (DEB) bereitgestellt.
- Die Weboberfläche ist nach der Installation standardmäßig über HTTP-Port 80 erreichbar.
- Die Grundinstallation enthält keine vorinstallierten Projekte.
- Installierte Projekte werden zentral erfasst und verwaltet.
- Die Bedienung erfolgt über eine übersichtliche Weboberfläche.

## 3. Benutzer- und Rollenmodell

Die IT-Projektzentrale unterstützt mehrere Benutzer und verwendet folgendes Rollenmodell (Variante C):

- **Administrator:** vollständige administrative Kontrolle über die IT-Projektzentrale.
- **Projektverwalter:** Verwaltung der dafür freigegebenen Projekte ohne Zugriff auf die Benutzer- und Rollenverwaltung oder auf übergreifende Sicherheitseinstellungen.
- **Benutzer mit Lesezugriff:** Anzeige des Dashboards ausschließlich mit den für den Benutzer freigegebenen Projekten, Projektinformationen und Projektverknüpfungen ohne verändernde Verwaltungsaktionen.

Berechtigungen werden nach dem Prinzip der geringsten erforderlichen Rechte vergeben. Für verändernde Projektaktionen gilt folgende Festlegung:

- Administratoren dürfen Projekte installieren, aktualisieren und löschen.
- Projektverwalter dürfen ausschließlich die ihnen zugewiesenen Projekte installieren, aktualisieren und löschen.
- Die Zuweisung von Projekten an Projektverwalter wird ausschließlich durch Administratoren vorgenommen.
- Benutzer mit Lesezugriff dürfen keine Projekte installieren, aktualisieren, löschen oder konfigurieren.
- Benutzer mit Lesezugriff sehen ausschließlich die Projekte, die ein Administrator für sie freigegeben hat; nicht freigegebene Projekte werden vollständig ausgeblendet.
- Die Benutzer- und Rollenverwaltung sowie übergreifende Sicherheitseinstellungen bleiben ausschließlich Administratoren vorbehalten.

Die Verwaltungsrechte eines Projektverwalters gelten nicht für nicht zugewiesene Projekte. Weitere Einzelrechte werden im weiteren Verlauf des Lastenhefts festgelegt.

## 4. Dashboard

- Das Dashboard zeigt alle installierten Projekte.
- Jedes installierte Projekt besitzt einen direkten Link zu seiner Weboberfläche.
- Zu jedem Projekt werden mindestens Name, Status, Version und Zieladresse angezeigt.
- Ist kein Projekt installiert, zeigt das Dashboard einen verständlichen Leerzustand.

## 5. Projektinstallation

- Projekte können über die Weboberfläche als DEB-Paket installiert werden.
- Als Installationsquellen werden lokale Uploads, GitHub und Gitea unterstützt.
- Zugangsdaten und Tokens für GitHub und Gitea werden geschützt gespeichert.
- Vor der Installation werden Paketname, Version und Quelle angezeigt.
- Fehler während der Installation werden verständlich protokolliert und ausgegeben.

## 6. Projektaktualisierung

- Für installierte Projekte kann über die Weboberfläche nach Aktualisierungen gesucht werden.
- Aktualisierungen können aus der jeweils konfigurierten GitHub- oder Gitea-Quelle installiert werden.
- Vor einer Aktualisierung werden aktuelle und verfügbare Version angezeigt.
- Fehlgeschlagene Aktualisierungen dürfen den bisherigen funktionsfähigen Stand nicht unkontrolliert beschädigen.

## 7. Projektentfernung

- Installierte Projekte können über die Weboberfläche deinstalliert werden.
- Vor der Deinstallation ist eine eindeutige Bestätigung erforderlich.
- Die Anwendung weist darauf hin, ob Konfigurationen und Projektdaten erhalten oder entfernt werden.
- Nach erfolgreicher Deinstallation wird das Projekt aus dem Dashboard entfernt.

## 8. Projektverwaltung

- Projekte können mit Name, Beschreibung, Version, Webadresse und Installationsquelle verwaltet werden.
- GitHub- und Gitea-Verbindungen können je Projekt konfiguriert werden.
- Status und Erreichbarkeit eines Projekts werden nachvollziehbar dargestellt.
- Aktionen und technische Meldungen werden protokolliert.

## 9. Sicherheit

- Verwaltungsfunktionen sind nur für berechtigte Benutzer zugänglich.
- Passwörter und Zugriffstokens werden nicht im Klartext in der Weboberfläche oder in Protokollen ausgegeben.
- Installations-, Update- und Deinstallationsaktionen werden serverseitig validiert.
- Hochgeladene Pakete werden vor der Verarbeitung geprüft.
- Systembefehle werden ausschließlich mit kontrollierten Parametern ausgeführt.

## 10. Qualität und Betrieb

- Die Anwendung ist für Debian-basierte Systeme vorgesehen.
- Installation, Aktualisierung und Deinstallation der IT-Projektzentrale selbst sind dokumentiert.
- Fehler werden mit Zeitstempel und ausreichendem technischem Kontext protokolliert.
- Die Oberfläche ist auf Desktop, Tablet und Smartphone nutzbar.
- Anforderungen werden bei der Weiterentwicklung in diesem Dokument gepflegt.

## 11. Offene Konkretisierungen

- Verbleibende Einzelrechte der drei Benutzerrollen
- Unterstützte Debian- und Raspberry-Pi-OS-Versionen
- Sicherungs- und Wiederherstellungsverfahren
- Verhalten bei Abhängigkeitskonflikten zwischen DEB-Paketen
- Definition der Schnittstelle beziehungsweise Metadaten für verwaltete Projekte
- Umfang der automatischen Erreichbarkeits- und Gesundheitsprüfungen
