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

def resolve_mount_and_cache_paths(storage):
    """Resolves filesystem mount point and rclone cache dir from dashboard storage config."""
    mount_point = storage.get("mount_point")
    mount_base = storage.get("mount_base", MOUNT_BASE)
    if not mount_point:
        parts = [p for p in mount_base.strip("/").split("/") if p]
        if len(parts) >= 2 and parts[0] in ("mnt", "media"):
            mount_point = f"/{parts[0]}/{parts[1]}"
        else:
            mount_point = mount_base

    cache_dir = storage.get("cache_dir")
    cache_base = storage.get("cache_base", CACHE_BASE)
    if not cache_dir:
        if "/vfs" in cache_base:
            cache_dir = cache_base.split("/vfs")[0]
        else:
            cache_dir = cache_base

    return mount_point, cache_dir

def check_rclone_mount():
    """Checks whether a primary_remote is configured."""
    remote = get_primary_remote()
    if not remote:
        print("[!] No primary_remote configured in Immiclone config.", file=sys.stderr)
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

    mount_point, cache_dir = resolve_mount_and_cache_paths(storage)
    vfs_cache_max_gb = storage.get("vfs_cache_max_gb", 10.0)
    rclone_conf = os.path.expanduser(storage.get("rclone_conf_path", RCLONE_CONF_PATH))
    rclone_rc_url = storage.get("rclone_rc_url", RCLONE_RC_URL)

    # Resolve rc-addr binding (default 0.0.0.0:5572)
    parsed_rc = urllib.parse.urlparse(rclone_rc_url if "://" in rclone_rc_url else f"http://{rclone_rc_url}")
    rc_port = parsed_rc.port or 5572
    rc_addr = f"0.0.0.0:{rc_port}"

    try:
        os.makedirs(mount_point, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)
    except Exception as e:
        print(f"[!] Warning creating mount/cache directories: {e}", file=sys.stderr)

    cmd = [
        "rclone", "mount", remote, mount_point,
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
        "--cache-dir", cache_dir,
        "--rc",
        "--rc-web-gui",
        "--rc-web-gui-no-open-browser",
        "--rc-addr", rc_addr,
        "--rc-no-auth"
    ]

    print(f"--> [Immiclone Mount] Mounting remote '{remote}' at '{mount_point}' (Cache: {cache_dir}, Limit: {vfs_cache_max_gb}G, RC: {rc_addr})")
    sys.stdout.flush()

    if os.name != "nt":
        # On Linux/Unix, execvp replaces current process so systemd tracks rclone directly
        os.execvp("rclone", cmd)
    else:
        # Windows fallback (e.g. for testing)
        subprocess.run(cmd)

def run_rclone_unmount():
    """Unmounts the configured mount using fusermount3."""
    cfg = get_app_config()
    storage = cfg.get("storage", {})
    mount_point, _ = resolve_mount_and_cache_paths(storage)

    print(f"--> [Immiclone Mount] Unmounting '{mount_point}'...")
    sys.stdout.flush()

    if os.name != "nt":
        for unmount_bin in ["/bin/fusermount3", "fusermount3", "/bin/fusermount", "fusermount"]:
            res = subprocess.run([unmount_bin, "-u", "-z", mount_point], capture_output=True)
            if res.returncode == 0:
                print(f"[✓] Successfully unmounted '{mount_point}'.")
                return
        subprocess.run(["umount", "-l", mount_point], check=False)
