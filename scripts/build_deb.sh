#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
APP_VERSION=$(tr -d '[:space:]' < "$ROOT_DIR/version.txt")
DEBIAN_VERSION=${APP_VERSION/-beta./~beta}
PACKAGE_NAME="it-projektzentrale_${APP_VERSION}_all.deb"
BUILD_DIR=$(mktemp -d)
PACKAGE_ROOT="$BUILD_DIR/package"

cleanup() { rm -rf "$BUILD_DIR"; }
trap cleanup EXIT

mkdir -p "$PACKAGE_ROOT/DEBIAN" "$PACKAGE_ROOT/opt/it-projektzentrale" \
  "$PACKAGE_ROOT/usr/lib/it-projektzentrale" "$PACKAGE_ROOT/etc/nginx/sites-available" \
  "$PACKAGE_ROOT/etc/systemd/system" "$ROOT_DIR/dist"

cp -a "$ROOT_DIR/app" "$ROOT_DIR/templates" "$ROOT_DIR/static" "$ROOT_DIR/nginx" \
  "$ROOT_DIR/systemd" "$ROOT_DIR/requirements.txt" "$ROOT_DIR/version.txt" \
  "$ROOT_DIR/README.md" "$ROOT_DIR/CHANGELOG.md" "$ROOT_DIR/CHATGPT_PROJEKTKONTEXT.md" \
  "$ROOT_DIR/NEUER_CHAT.md" "$ROOT_DIR/install.sh" "$PACKAGE_ROOT/opt/it-projektzentrale/"
rm -rf "$PACKAGE_ROOT/opt/it-projektzentrale/app/__pycache__"

install -m 0644 "$ROOT_DIR/nginx/it-projektzentrale.conf" "$PACKAGE_ROOT/etc/nginx/sites-available/it-projektzentrale.conf"
install -m 0644 "$ROOT_DIR/systemd/it-projektzentrale.service" "$PACKAGE_ROOT/etc/systemd/system/it-projektzentrale.service"
install -m 0644 "$ROOT_DIR/systemd/it-projektzentrale-worker.service" "$PACKAGE_ROOT/etc/systemd/system/it-projektzentrale-worker.service"
install -m 0755 "$ROOT_DIR/scripts/itpz-helper" "$PACKAGE_ROOT/usr/lib/it-projektzentrale/itpz-helper"
install -m 0700 "$ROOT_DIR/scripts/itpz-helper" "$PACKAGE_ROOT/usr/lib/it-projektzentrale/itpz-helper-worker"
install -m 0755 "$ROOT_DIR/scripts/itpz-install-worker" "$PACKAGE_ROOT/usr/lib/it-projektzentrale/itpz-install-worker"
install -m 0755 "$ROOT_DIR/scripts/itpz-compose-helper" "$PACKAGE_ROOT/usr/lib/it-projektzentrale/itpz-compose-helper"

sed "s/@DEBIAN_VERSION@/$DEBIAN_VERSION/" "$ROOT_DIR/debian/control.in" > "$PACKAGE_ROOT/DEBIAN/control"
install -m 0644 "$ROOT_DIR/debian/conffiles" "$PACKAGE_ROOT/DEBIAN/conffiles"
install -m 0755 "$ROOT_DIR/debian/postinst" "$PACKAGE_ROOT/DEBIAN/postinst"
install -m 0755 "$ROOT_DIR/debian/prerm" "$PACKAGE_ROOT/DEBIAN/prerm"
install -m 0755 "$ROOT_DIR/debian/postrm" "$PACKAGE_ROOT/DEBIAN/postrm"

VERSION_SOURCE="$ROOT_DIR/app/main.py"
for candidate in "$ROOT_DIR"/app/v*.py; do
  [[ -f "$candidate" ]] || continue
  VERSION_SOURCE="$candidate"
done
SOURCE_VERSION=$(sed -n 's/^VERSION = "\([^"]*\)"/\1/p' "$VERSION_SOURCE")
if [[ "$SOURCE_VERSION" != "$APP_VERSION" ]]; then
  echo "Versionsfehler: ${VERSION_SOURCE#$ROOT_DIR/}=$SOURCE_VERSION, version.txt=$APP_VERSION" >&2
  exit 1
fi

dpkg-deb --root-owner-group --build "$PACKAGE_ROOT" "$ROOT_DIR/dist/$PACKAGE_NAME"
sha256sum "$ROOT_DIR/dist/$PACKAGE_NAME" > "$ROOT_DIR/dist/$PACKAGE_NAME.sha256"
echo "$ROOT_DIR/dist/$PACKAGE_NAME"
