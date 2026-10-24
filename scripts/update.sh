#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# IMMICLONE AUTO-UPDATE SCRIPT
# Performs safe git pull and zero-downtime service reload.
# ==============================================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Updating Immich Duplication Control Center (Immiclone)..."
cd "${REPO_DIR}"

# 1. Pull latest changes
git pull --ff-only

# 2. Ensure executable permissions and symlinks
chmod +x "${REPO_DIR}/dashboard/server.py"
chmod +x "${REPO_DIR}/worker/worker.sh"
chmod +x "${REPO_DIR}/scripts/"*.sh
ln -sf "${REPO_DIR}/dashboard/server.py" /usr/local/bin/immiclone 2>/dev/null || true
ln -sf /usr/local/bin/immiclone /usr/local/bin/immich-cache-dashboard.py 2>/dev/null || true

# 3. Reload dashboard without affecting Immich containers or Rclone mounts
echo "--> Restarting immiclone service..."
if systemctl is-active --quiet immiclone.service 2>/dev/null; then
  sudo systemctl restart immiclone.service
elif systemctl is-active --quiet immich-cache-dashboard.service 2>/dev/null; then
  sudo systemctl restart immich-cache-dashboard.service
else
  sudo systemctl restart immiclone.service
fi

echo "==> Successfully updated! Service is running latest commit:"
git log -1 --oneline
