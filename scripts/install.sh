#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# IMMICLONE STORAGE & DUPLICATION CONTROL CENTER INSTALLER
# ==============================================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing Immiclone Storage & Duplication Control Center from: ${REPO_DIR}"

if [[ $EUID -ne 0 ]]; then
   echo "[!] This script must be run as root (use sudo)."
   exit 1
fi

# 1. Symlink dashboard executables to /usr/local/bin
echo "--> Linking dashboard executables to /usr/local/bin/immiclone..."
chmod +x "${REPO_DIR}/dashboard/server.py"
chmod +x "${REPO_DIR}/worker/worker.sh"
chmod +x "${REPO_DIR}/scripts/"*.sh
ln -sf "${REPO_DIR}/dashboard/server.py" /usr/local/bin/immiclone
ln -sf /usr/local/bin/immiclone /usr/local/bin/immich-cache-dashboard.py

# 2. Install systemd unit files
echo "--> Installing systemd services..."
cp "${REPO_DIR}/systemd/immiclone.service" /etc/systemd/system/immiclone.service

# Keep legacy service name aliased/symlinked for backward compatibility
if [[ ! -e /etc/systemd/system/immich-cache-dashboard.service || -L /etc/systemd/system/immich-cache-dashboard.service ]]; then
  ln -sf /etc/systemd/system/immiclone.service /etc/systemd/system/immich-cache-dashboard.service
fi

# Install Rclone service template if no existing mount service exists
if [[ ! -f /etc/systemd/system/immiclone-rclone.service && ! -f /etc/systemd/system/rclone-gda.service ]]; then
  echo "--> Installing default immiclone-rclone.service template..."
  cp "${REPO_DIR}/systemd/immiclone-rclone.service" /etc/systemd/system/immiclone-rclone.service
fi

# 3. Migrate from legacy immich-cache-dashboard if currently active
if systemctl is-active --quiet immich-cache-dashboard.service 2>/dev/null; then
  echo "--> Migrating from legacy immich-cache-dashboard.service..."
  systemctl stop immich-cache-dashboard.service || true
fi

# 4. Reload systemd and start immiclone service
echo "--> Reloading systemd and enabling immiclone service..."
systemctl daemon-reload
systemctl enable immiclone.service
systemctl restart immiclone.service

echo "==> Installation complete! Service status:"
systemctl status immiclone.service --no-pager
