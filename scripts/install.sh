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

# 1. Ensure executable permissions
echo "--> Setting executable permissions..."
chmod +x "${REPO_DIR}/dashboard/server.py"
chmod +x "${REPO_DIR}/worker/worker.sh"
chmod +x "${REPO_DIR}/scripts/"*.sh

# 2. Symlink main binary to /usr/local/bin/immiclone
echo "--> Linking executable to /usr/local/bin/immiclone..."
ln -sf "${REPO_DIR}/dashboard/server.py" /usr/local/bin/immiclone

# 3. Clean up legacy services (immich-cache-dashboard & rclone-gda)
if systemctl is-active --quiet immich-cache-dashboard.service 2>/dev/null; then
  echo "--> Stopping legacy immich-cache-dashboard.service..."
  systemctl stop immich-cache-dashboard.service || true
fi
if systemctl is-enabled --quiet immich-cache-dashboard.service 2>/dev/null; then
  echo "--> Disabling legacy immich-cache-dashboard.service..."
  systemctl disable immich-cache-dashboard.service || true
fi
rm -f /etc/systemd/system/immich-cache-dashboard.service /usr/local/bin/immich-cache-dashboard.py

if systemctl is-active --quiet rclone-gda.service 2>/dev/null; then
  echo "--> Stopping legacy rclone-gda.service..."
  systemctl stop rclone-gda.service || true
fi
if systemctl is-enabled --quiet rclone-gda.service 2>/dev/null; then
  echo "--> Disabling legacy rclone-gda.service..."
  systemctl disable rclone-gda.service || true
fi
rm -f /etc/systemd/system/rclone-gda.service

# 4. Install updated systemd services
echo "--> Installing immiclone.service and immiclone-rclone.service..."
cp "${REPO_DIR}/systemd/immiclone.service" /etc/systemd/system/immiclone.service
cp "${REPO_DIR}/systemd/immiclone-rclone.service" /etc/systemd/system/immiclone-rclone.service

# 5. Reload systemd daemon
echo "--> Reloading systemd daemon..."
systemctl daemon-reload

# 6. Enable and start services
echo "--> Enabling and starting immiclone service..."
systemctl enable immiclone.service
systemctl restart immiclone.service

systemctl enable immiclone-rclone.service
# Only start rclone mount if primary_remote is configured
if /usr/local/bin/immiclone --mount-check 2>/dev/null || true; then
  systemctl restart immiclone-rclone.service || true
fi

echo "==> Installation complete! Service status:"
systemctl status immiclone.service --no-pager
