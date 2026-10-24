#!/usr/bin/env python3
"""
Immiclone Rclone VFS Mount Service
Dynamically mounts the configured primary_remote and storage paths
from the Immiclone dashboard configuration.
"""
import os
import sys
import subprocess
import urllib.parse
from dashboard.config import (
    get_app_config,
    get_primary_remote,
    MOUNT_BASE,
    CACHE_BASE,
    RCLONE_CONF_PATH,
    RCLONE_RC_URL
)

def check_rclone_mount():
    """Checks whether a primary_remote is configured."""
    remote = get_primary_remote()
    if not remote:
        print("[!] No primary_remote configured in Immiclone config.")
        sys.exit(1)
    print(f"[✓] Configured primary_remote: {remote}")
    sys.exit(0)

def run_rclone_mount():
    """Starts rclone mount directly using settings from Immiclone dashboard config."""
    cfg = get_app_config()
    storage = cfg.get("storage", {})
    remote = get_primary_remote()

    if not remote:
        print("[!] Error: No primary_remote configured in Immiclone dashboard config.", file=sys.stderr)
        print("    Configure 'primary_remote' in the web UI Settings (port 8080) or app_config.json.", file=sys.stderr)
        sys.exit(1)

    mount_base = storage.get("mount_base", MOUNT_BASE)
    cache_base = storage.get("cache_base", CACHE_BASE)
    vfs_cache_max_gb = storage.get("vfs_cache_max_gb", 10.0)
    rclone_conf = os.path.expanduser(storage.get("rclone_conf_path", RCLONE_CONF_PATH))
    rclone_rc_url = storage.get("rclone_rc_url", RCLONE_RC_URL)

    # Resolve rc-addr binding (default 0.0.0.0:5572)
    parsed_rc = urllib.parse.urlparse(rclone_rc_url if "://" in rclone_rc_url else f"http://{rclone_rc_url}")
    rc_port = parsed_rc.port or 5572
    rc_addr = f"0.0.0.0:{rc_port}"

    try:
        os.makedirs(mount_base, exist_ok=True)
        os.makedirs(cache_base, exist_ok=True)
    except Exception as e:
        print(f"[!] Warning creating mount/cache directories: {e}", file=sys.stderr)

    cmd = [
        "rclone", "mount", remote, mount_base,
        "--config", rclone_conf,
        "--allow-other",
        "--uid=1000",
        "--gid=1000",
        "--umask", "0002",
        "--dir-cache-time", "12h",
        "--poll-interval", "1m",
        "--vfs-cache-mode", "full",
        "--vfs-cache-max-size", f"{vfs_cache_max_gb}G",
        "--vfs-cache-max-age", "24h",
        "--cache-dir", cache_base,
        "--rc",
        "--rc-web-gui",
        "--rc-web-gui-no-open-browser",
        "--rc-addr", rc_addr,
        "--rc-no-auth"
    ]

    print(f"--> [Immiclone Mount] Mounting '{remote}' -> '{mount_base}' (Cache: {cache_base}, Limit: {vfs_cache_max_gb}G, RC: {rc_addr})")
    sys.stdout.flush()

    if os.name != "nt":
        # On Linux/Unix, execvp replaces the current Python process so systemd tracks rclone directly
        os.execvp("rclone", cmd)
    else:
        # Windows fallback (e.g. for testing)
        subprocess.run(cmd)

def run_rclone_unmount():
    """Unmounts the configured mount_base using fusermount3."""
    cfg = get_app_config()
    mount_base = cfg.get("storage", {}).get("mount_base", MOUNT_BASE)

    print(f"--> [Immiclone Mount] Unmounting '{mount_base}'...")
    sys.stdout.flush()

    if os.name != "nt":
        # Try fusermount3 first, fallback to fusermount or umount
        for unmount_bin in ["/bin/fusermount3", "fusermount3", "/bin/fusermount", "fusermount"]:
            res = subprocess.run([unmount_bin, "-u", "-z", mount_base], capture_output=True)
            if res.returncode == 0:
                print(f"[✓] Successfully unmounted '{mount_base}'.")
                return
        subprocess.run(["umount", "-l", mount_base], check=False)
