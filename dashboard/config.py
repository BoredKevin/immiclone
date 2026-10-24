import os
import json
import secrets
import threading

# Base Directories (using realpath to resolve any symlinks cleanly)
DASHBOARD_DIR = os.path.dirname(os.path.realpath(__file__))
TEMPLATES_DIR = os.path.join(DASHBOARD_DIR, "templates")
STATIC_DIR = os.path.join(DASHBOARD_DIR, "static")

# Environment & Server Ports
PORT = int(os.environ.get("PORT", 8080))

# Storage Mounts & Caching Paths
MOUNT_BASE = os.environ.get("MOUNT_BASE", "/mnt/gda/library/library")
CACHE_BASE = os.environ.get("CACHE_BASE", "/var/cache/rclone-gda/vfs/bkc/library/library")
RCLONE_CONF_PATH = os.environ.get("RCLONE_CONF_PATH", "/root/.config/rclone/rclone.conf")

# Persistent State Stores (Survives reboots & updates)
TX_STORE_PATH = os.environ.get("TX_STORE_PATH", "/home/kevin/immich-app/duplication_transactions.json")
WORKERS_STORE_PATH = os.environ.get("WORKERS_STORE_PATH", "/home/kevin/immich-app/workers_registry.json")
TAILSCALE_CONF_PATH = os.environ.get("TAILSCALE_CONF_PATH", "/home/kevin/immich-app/tailscale_config.json")

# Split Domain Locks
# STATE_LOCK: In-memory worker/transaction mutations & fast atomic JSON writes
STATE_LOCK = threading.RLock()
# SCAN_LOCK: Filesystem walks in scanner.py (prevents Fuse mounts from blocking telemetry)
SCAN_LOCK = threading.Lock()

def format_size(bytes_size):
    """Formats bytes into human-readable representation."""
    if bytes_size is None or bytes_size < 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"

def atomic_write_json(filepath, data):
    """Safely writes JSON data atomically on the same filesystem."""
    target_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(target_dir, exist_ok=True)
    tmp_path = f"{filepath}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, filepath)
        return True
    except Exception as e:
        print(f"[!] Error writing atomic JSON to {filepath}: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
        return False
