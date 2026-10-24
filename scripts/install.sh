#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# BABEL STORAGE & DUPLICATION CONTROL CENTER INSTALLER
# ==============================================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing Babel Storage & Duplication Control Center from: ${REPO_DIR}"

if [[ $EUID -ne 0 ]]; then
   echo "[!] This script must be run as root (use sudo)."
   exit 1
fi

# 1. Symlink dashboard to /usr/local/bin
echo "--> Linking dashboard script to /usr/local/bin/immich-cache-dashboard.py"
chmod +x "${REPO_DIR}/dashboard/server.py"
ln -sf "${REPO_DIR}/dashboard/server.py" /usr/local/bin/immich-cache-dashboard.py

# 2. Install or update systemd unit files
echo "--> Installing systemd services..."
cp "${REPO_DIR}/systemd/immich-cache-dashboard.service" /etc/systemd/system/immich-cache-dashboard.service

if [[ ! -f /etc/systemd/system/rclone-gda.service ]]; then
  cp "${REPO_DIR}/systemd/rclone-gda.service" /etc/systemd/system/rclone-gda.service
fi

# 3. Reload systemd and restart dashboard
echo "--> Reloading systemd and restarting dashboard service..."
systemctl daemon-reload
systemctl enable immich-cache-dashboard.service
systemctl restart immich-cache-dashboard.service

echo "==> Installation complete! Service status:"
systemctl status immich-cache-dashboard.service --no-pager
