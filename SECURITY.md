# Sicherheitsrichtlinie

## Unterstützte Versionen

Derzeit ist noch keine Version für den Produktivbetrieb freigegeben. `1.0.0-beta.1` ist ausschließlich ein technischer Teststand.

## Niemals in GitHub speichern

- Passwörter und produktive Initialpasswörter
- GitHub-, Gitea- oder sonstige Zugangstokens
- private Schlüssel
- produktive `.env`- und Konfigurationsdateien
- Datenbanken, Backups, Uploads, Protokolle oder Kundendaten

## Schwachstellen melden

Ausnutzbare Details nicht in einer öffentlichen Issue veröffentlichen. Bis ein eigener Meldeweg festgelegt ist, den Repository-Eigentümer direkt und vertraulich kontaktieren.

## Freigaberegel

Ein Release erhält erst nach erfolgreicher Authentifizierungs-, Berechtigungs-, CSRF-, Paket-, Update-, Backup- und Deinstallationsprüfung eine Produktivfreigabe.

