#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Bitte als root ausführen." >&2; exit 1; }
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

command -v dpkg-deb >/dev/null 2>&1 || {
    apt-get update
    apt-get install -y dpkg
}

bash "$ROOT_DIR/scripts/build_deb.sh"
VERSION=$(tr -d '[:space:]' < "$ROOT_DIR/version.txt")
PACKAGE="$ROOT_DIR/dist/it-projektzentrale_${VERSION}_all.deb"
[[ -f "$PACKAGE" ]] || { echo "Paketbau fehlgeschlagen." >&2; exit 1; }

sha256sum -c "$PACKAGE.sha256"
apt-get install -y "$PACKAGE"
