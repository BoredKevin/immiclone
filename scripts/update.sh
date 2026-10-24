#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# BABEL AUTO-UPDATE SCRIPT
# Performs safe git pull and zero-downtime service reload.
# ==============================================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Updating Babel Storage & Duplication Control Center..."
cd "${REPO_DIR}"

# 1. Pull latest changes
git pull --ff-only

# 2. Ensure executable permissions
chmod +x "${REPO_DIR}/dashboard/server.py"
chmod +x "${REPO_DIR}/worker/worker.sh"
chmod +x "${REPO_DIR}/scripts/"*.sh

# 3. Reload dashboard without affecting Immich containers or Rclone mounts
echo "--> Restarting immich-cache-dashboard service..."
sudo systemctl restart immich-cache-dashboard.service

echo "==> Successfully updated! Service is running latest commit:"
git log -1 --oneline
