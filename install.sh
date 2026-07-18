#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Bitte als root ausführen."; exit 1; }
apt-get update
apt-get install -y python3 python3-venv nginx sudo
id it-projektzentrale >/dev/null 2>&1 || useradd --system --home /opt/it-projektzentrale --shell /usr/sbin/nologin it-projektzentrale
mkdir -p /opt/it-projektzentrale
cp -a app templates static data uploads requirements.txt version.txt /opt/it-projektzentrale/
python3 -m venv /opt/it-projektzentrale/.venv
/opt/it-projektzentrale/.venv/bin/pip install --upgrade pip
/opt/it-projektzentrale/.venv/bin/pip install -r /opt/it-projektzentrale/requirements.txt
chown -R it-projektzentrale:it-projektzentrale /opt/it-projektzentrale
install -m 0644 systemd/it-projektzentrale.service /etc/systemd/system/it-projektzentrale.service
install -m 0644 nginx/it-projektzentrale.conf /etc/nginx/sites-available/it-projektzentrale
rm -f /etc/nginx/sites-enabled/it-projektzentrale
ln -sfn /etc/nginx/sites-available/it-projektzentrale /etc/nginx/sites-enabled/it-projektzentrale.conf
rm -f /etc/nginx/sites-enabled/default
cat >/etc/it-projektzentrale.conf <<CONF
ITPZ_SECRET=$(openssl rand -hex 32)
ITPZ_ADMIN_USER=admin
ITPZ_ADMIN_PASSWORD=admin
CONF
cat >/etc/sudoers.d/it-projektzentrale <<'SUDO'
it-projektzentrale ALL=(root) NOPASSWD: /usr/bin/apt-get install -y /opt/it-projektzentrale/uploads/packages/*.deb
SUDO
chmod 440 /etc/sudoers.d/it-projektzentrale
systemctl daemon-reload
nginx -t
systemctl enable --now it-projektzentrale nginx
echo "Installation abgeschlossen: http://$(hostname -I | awk '{print $1}')/"
echo "Admin: admin / admin – Passwort in /etc/it-projektzentrale.conf ändern."
