# Plugin-Manifest `projekt.yaml`

Version 1.5.0 führt einen deklarativen Plugin-Standard ein. Das Manifest registriert ein Projekt in der IT-Projektzentrale, ohne beim Import Programmcode auszuführen.

## Beispiel

```yaml
manifest_version: "1"
id: contactsync
name: ContactSync Professional
version: 3.2.09
description: Synchronisiert Kontakte zwischen 3CX, Nextcloud, Zammad und Odoo.
category: Kommunikation
author: Markus
license: proprietär
homepage: https://example.invalid/contactsync
repository: https://github.com/Markus4771/contactsync
icon: icon.png

install:
  type: deb
  package: contactsync-professional

source:
  provider: github
  base_url: https://github.com
  repository: Markus4771/contactsync
  asset_pattern: "*.deb"

services:
  - contactsync-professional.service

health:
  url: https://example.invalid/health

capabilities:
  install: {}
  update: {}
  backup:
    strategy: application
  health:
    interval_seconds: 60
  dashboard: {}

permissions:
  - network
  - package-install
```

## Unterstützte Installationstypen

- `deb`
- `docker`
- `compose`
- `external`
- `manual`

Version 1.5.0 registriert alle Typen. Die automatische Installation ist zunächst nur für `deb` vollständig verdrahtet.

## Unterstützte Fähigkeiten

`install`, `update`, `uninstall`, `backup`, `restore`, `health`, `settings`, `dashboard`, `logs`, `service-control`, `api` und `webhook`.

## Sicherheitsmodell

- YAML wird mit `safe_load` gelesen.
- Die Dateigröße ist auf 512 KiB begrenzt.
- IDs, Paketnamen, Dienste, URLs und Repository-Angaben werden validiert.
- Unbekannte Fähigkeiten werden abgewiesen.
- Beim Import werden keine Skripte und kein Plugin-Pythoncode ausgeführt.
- Das Feld „vertrauenswürdig“ ist eine manuelle Kennzeichnung und keine kryptografische Signatur.
- Debian-Pakete werden weiterhin ausschließlich über den abgesicherten Root-Helfer installiert.

## Weitere Entwicklung

Geplant sind signierte Manifestkataloge, Abhängigkeitsauflösung, Plugin-Einstellungen, Dashboard-Widgets, Health-Worker sowie sichere Backup- und Restore-Hooks.
