# Sicherheitsrichtlinie

## Unterstützte Versionen

Derzeit ist noch keine Version für den Produktivbetrieb freigegeben. `1.0.0-beta.2` ist ein gehärteter Teststand. Die Beta 1 ist nicht mehr unterstützt.

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

Die aktuell offenen Punkte und die Grenzen des Root-Helfers sind in [`docs/security/SECURITY_REVIEW_1.0.0-beta.2.md`](docs/security/SECURITY_REVIEW_1.0.0-beta.2.md) dokumentiert. Nur Pakete aus vertrauenswürdiger Quelle dürfen installiert werden: Debian-Pakete führen während der Installation privilegierte Maintainer-Skripte aus.
