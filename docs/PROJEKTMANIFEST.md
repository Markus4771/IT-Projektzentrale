# IT-Projektzentrale Projektmanifest

Version 3.2.0 führt das Manifest `projekt.yaml` mit dem Schema `itpz/v1` ein.

## Ablage

Lokale Projekte werden standardmäßig erkannt unter:

- `/srv/itpz-projects/<projekt>/projekt.yaml`
- `/opt/itpz-projects/<projekt>/projekt.yaml`

Weitere absolute Suchpfade können in `/etc/it-projektzentrale.conf` gesetzt werden:

```ini
ITPZ_PROJECT_SCAN_ROOTS=/srv/itpz-projects:/opt/itpz-projects
```

## Beispiel

```yaml
schema: itpz/v1
id: contactsync
name: ContactSync Professional
version: 3.2.9
type: deb
channel: stable
category: Kommunikation
description: Synchronisiert Kontakte zwischen mehreren Plattformen.
homepage: https://contactsync.example.test

package:
  name: contactsync-professional
  asset: contactsync_*.deb

source:
  provider: github
  repository: Markus4771/contactsync

install:
  service: contactsync-professional.service

health:
  type: http
  url: http://127.0.0.1:8080/health

dependencies:
  - id: nextcloud
    optional: true

permissions:
  - network
  - database-write
```

## Pflichtfelder

- `id`: stabile Kennung aus Kleinbuchstaben, Zahlen und Bindestrichen
- `name`: sichtbarer Projektname
- `version`: Projektversion
- `type`: `deb`, `compose`, `script`, `plugin` oder `external`

## Release-Kanäle

- `stable`
- `beta`
- `development`

## Quellen

Unterstützte Anbieter:

- `github`
- `gitea`
- `local`

Für GitHub und Gitea muss `repository` die Form `Eigentümer/Repository` besitzen.

## Berechtigungen

Zulässig sind ausschließlich:

- `network`
- `filesystem-read`
- `filesystem-write`
- `database-read`
- `database-write`
- `notifications`
- `server-status`
- `systemd`
- `docker`

Das Manifest führt keine Befehle direkt aus. Es beschreibt das Projekt und wird erst nach Validierung und ausdrücklicher Übernahme durch einen Administrator in den Projekt- und Installationskatalog eingetragen.
