# IT-Projektzentrale Projekt-SDK

Das Projekt-SDK definiert den Integrationsvertrag zwischen einem Softwareprojekt und der IT-Projektzentrale.

## Mindestanforderungen

1. `projekt.yaml` im Wurzelverzeichnis des Repositories.
2. Eindeutige Projekt-ID und semantische Version.
3. Installierbares Debian-Paket oder ein anderer unterstützter Projekttyp.
4. Eindeutiges Release-Asset-Muster.
5. SHA256-Prüfsumme des veröffentlichten Pakets.
6. Optional ein systemd-Dienst und ein lokaler Health-Endpunkt.

## Empfohlener Releaseablauf

- Debian-Paket bauen.
- SHA256-Prüfsumme erzeugen.
- Manifestversion und Prüfsumme aktualisieren.
- Git-Tag und Release erstellen.
- Paket als Release-Asset veröffentlichen.
- Repository-Erkennung in der IT-Projektzentrale starten.
- Manifest prüfen und ausdrücklich in den App-Store übernehmen.

## Sicherheitsmodell

Die IT-Projektzentrale führt keine Befehle aus dem Manifest aus. Felder, Berechtigungen, Quellen und Paketnamen werden validiert. Ein automatischer Paketdownload benötigt HTTPS und eine gültige SHA256-Prüfsumme. Zugangstokens werden ausschließlich über die verschlüsselte Secret-Verwaltung referenziert.

## Health-Endpunkt

Empfohlen wird ein lokaler Endpunkt wie `http://127.0.0.1:8080/health`, der bei Erfolg HTTP 200 und mindestens `status` sowie `version` liefert.

## Vorlage

Die aktuelle Vorlage befindet sich unter `sdk/projekt.example.yaml` und in der Weboberfläche unter **Projekt-SDK**.
