#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VERSION=$(tr -d '[:space:]' < "$ROOT/version.txt")
BUILD=$(mktemp -d); trap 'rm -rf "$BUILD"' EXIT
P="$BUILD/package"; mkdir -p "$P/DEBIAN" "$P/usr/lib/itpz-agent" "$P/etc/systemd/system" "$P/var/lib/itpz-agent/packages" "$ROOT/dist"
install -m 0755 "$ROOT/agent/itpz-agent.py" "$P/usr/lib/itpz-agent/itpz-agent.py"
install -m 0644 "$ROOT/agent/itpz-agent.service" "$P/etc/systemd/system/itpz-agent.service"
cat > "$P/DEBIAN/control" <<EOF
Package: itpz-agent
Version: $VERSION
Section: admin
Priority: optional
Architecture: all
Depends: python3, apt
Maintainer: IT-Projektzentrale
Description: Sicherer Remote-Agent für IT-Projektzentrale
EOF
cat > "$P/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -eu
install -d -m 0700 /var/lib/itpz-agent /var/lib/itpz-agent/packages /var/lib/itpz-agent/backups /var/lib/itpz-agent/jobs
if [ ! -f /etc/itpz-agent.conf ]; then
  umask 077
  cat > /etc/itpz-agent.conf <<CONF
ITPZ_AGENT_TOKEN_HASH=
ITPZ_AGENT_HOST=0.0.0.0
ITPZ_AGENT_PORT=8765
ITPZ_AGENT_STATE=/var/lib/itpz-agent
CONF
fi
chmod 0600 /etc/itpz-agent.conf
systemctl daemon-reload
systemctl enable itpz-agent.service >/dev/null 2>&1 || true
if grep -Eq '^ITPZ_AGENT_TOKEN_HASH=.{32,}$' /etc/itpz-agent.conf; then systemctl restart itpz-agent.service; fi
exit 0
EOF
cat > "$P/DEBIAN/prerm" <<'EOF'
#!/bin/sh
systemctl stop itpz-agent.service 2>/dev/null || true
exit 0
EOF
chmod 0755 "$P/DEBIAN/postinst" "$P/DEBIAN/prerm"
OUT="$ROOT/dist/itpz-agent_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$P" "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
echo "$OUT"
