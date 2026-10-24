import os
import json
import secrets
import threading
import subprocess

# Application Versioning & Semantic Version Standard
APP_VERSION = "1.0.0"
API_VERSION = "v1"

def get_git_info():
    """Resolves current git commit SHA and active branch with disk fallbacks."""
    commit = "unknown"
    branch = "main"

    # 1. Try Git CLI first
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_DIR,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=REPO_DIR,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return commit, branch
    except Exception:
        pass

    # 2. File-based fallback reading .git directly
    try:
        git_dir = os.path.join(REPO_DIR, ".git")
        head_path = os.path.join(git_dir, "HEAD")
        if os.path.isfile(head_path):
            with open(head_path, "r", encoding="utf-8") as f:
                head_content = f.read().strip()
            if head_content.startswith("ref:"):
                ref_rel = head_content[4:].strip()
                branch = os.path.basename(ref_rel)
                ref_path = os.path.join(git_dir, ref_rel)
                if os.path.isfile(ref_path):
                    with open(ref_path, "r", encoding="utf-8") as rf:
                        commit = rf.read().strip()
            else:
                commit = head_content
    except Exception:
        pass

    return commit, branch

def get_version_metadata():
    """Returns structured SemVer and repository metadata."""
    commit, branch = get_git_info()
    return {
        "app_name": get_app_name(),
        "version": APP_VERSION,
        "version_tag": f"v{APP_VERSION}",
        "semver": {
            "major": 1,
            "minor": 0,
            "patch": 0,
            "prerelease": None,
            "build": commit[:7] if commit != "unknown" else None
        },
        "api_version": API_VERSION,
        "git": {
            "commit": commit,
            "commit_short": commit[:7] if commit != "unknown" else "unknown",
            "branch": branch
        }
    }

# Base Directories (using realpath to resolve any symlinks cleanly)
DASHBOARD_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.dirname(DASHBOARD_DIR)
TEMPLATES_DIR = os.path.join(DASHBOARD_DIR, "templates")
STATIC_DIR = os.path.join(DASHBOARD_DIR, "static")
WORKER_SCRIPT_PATH = os.path.join(REPO_DIR, "worker", "worker.sh")

# Environment & Server Ports
PORT = int(os.environ.get("PORT", 8080))

# Dynamic Data Directory Resolution
def get_default_data_dir():
    """Resolves persistent data storage directory with graceful backward compatibility."""
    if os.environ.get("DATA_DIR"):
        return os.environ.get("DATA_DIR")
    # Preserve legacy path if present on Babel host
    legacy_dir = "/home/kevin/immich-app"
    if os.path.isdir(legacy_dir):
        return legacy_dir
    # User home fallback (~/.immiclone) or local repo data/
    home_dir = os.path.expanduser("~")
    immiclone_dir = os.path.join(home_dir, ".immiclone")
    if os.path.exists(immiclone_dir) or os.name != "nt":
        return immiclone_dir
    return os.path.join(REPO_DIR, "data")

DATA_DIR = get_default_data_dir()

# Persistent State Stores (Survives reboots & updates)
TX_STORE_PATH = os.environ.get("TX_STORE_PATH", os.path.join(DATA_DIR, "duplication_transactions.json"))
WORKERS_STORE_PATH = os.environ.get("WORKERS_STORE_PATH", os.path.join(DATA_DIR, "workers_registry.json"))
TAILSCALE_CONF_PATH = os.environ.get("TAILSCALE_CONF_PATH", os.path.join(DATA_DIR, "tailscale_config.json"))
APP_CONFIG_PATH = os.environ.get("APP_CONFIG_PATH", os.path.join(DATA_DIR, "app_config.json"))

# Storage Mounts & Caching Paths (environment fallbacks)
MOUNT_BASE = os.environ.get("MOUNT_BASE", "/mnt/gda/library/library")
CACHE_BASE = os.environ.get("CACHE_BASE", "/var/cache/rclone-gda/vfs/bkc/library/library")
RCLONE_CONF_PATH = os.environ.get("RCLONE_CONF_PATH", "/root/.config/rclone/rclone.conf")
RCLONE_RC_URL = os.environ.get("RCLONE_RC_URL", "http://localhost:5572")

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

# --------------------------------------------------------------------------
# UNIFIED APPLICATION SETTINGS STORE (app_config.json)
# --------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "general": {
        "app_name": "Immich & Duplication Control Center",
        "server_external_url": "", # e.g. "http://babel.ts.bkev.in:8080"
        "worker_cdn_url": "",      # e.g. "https://cdn.bkev.in/babel/worker.sh"
        "immich_web_url": "",      # e.g. "http://babel.ts.bkev.in:2283"
        "rclone_gui_url": ""       # e.g. "http://babel.ts.bkev.in:5572"
    },
    "storage": {
        "primary_remote": "bkc:",
        "mount_base": MOUNT_BASE,
        "cache_base": CACHE_BASE,
        "vfs_cache_max_gb": 10.0,
        "rclone_rc_url": RCLONE_RC_URL,
        "rclone_conf_path": RCLONE_CONF_PATH
    },
    "presets": [
        {
            "id": "raw-gdrive",
            "name": "Raw Google Drive Mirror",
            "source": "boredkevinmedia:crypt",
            "dest": "1337quota:crypt",
            "mode": "copy",
            "priority": "normal",
            "flags": "--transfers=8 --checkers=16 --fast-list --drive-server-side-across-configs",
            "description": "Drive-to-Drive optimized flags with fast-list and multi-stream transfers."
        },
        {
            "id": "raw-terabox",
            "name": "Raw Terabox Mirror",
            "source": "boredkevinmedia:crypt",
            "dest": "tb:crypt",
            "mode": "copy",
            "priority": "normal",
            "flags": "--size-only --transfers=4 --checkers=8 --tpslimit=4",
            "description": "Raw encrypted mirror directly to Terabox cloud."
        },
        {
            "id": "crypt-terabox",
            "name": "Decrypted Terabox Mirror",
            "source": "bkc:library",
            "dest": "tbc:library",
            "mode": "copy",
            "priority": "normal",
            "flags": "--size-only --transfers=4 --checkers=8 --tpslimit=4",
            "description": "Decrypts in RAM and re-encrypts with Terabox crypt keys."
        },
        {
            "id": "crypt-1337quota",
            "name": "Decrypted 1337quota Mirror",
            "source": "bkc:library",
            "dest": "1qc:library",
            "mode": "copy",
            "priority": "normal",
            "flags": "--transfers=8 --checkers=16 --fast-list --size-only",
            "description": "Decrypts in RAM and re-encrypts into 1qc crypt remote."
        }
    ]
}

_cached_config = None

def get_app_config():
    """Loads application settings with schema merging and in-memory cache."""
    global _cached_config
    with STATE_LOCK:
        if _cached_config is not None:
            return _cached_config

        loaded = {}
        if os.path.exists(APP_CONFIG_PATH):
            try:
                with open(APP_CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except Exception as e:
                print(f"[!] Error loading {APP_CONFIG_PATH}: {e}")

        # Deep merge defaults with loaded config
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        if isinstance(loaded, dict):
            for section in ("general", "storage"):
                if isinstance(loaded.get(section), dict):
                    merged[section].update(loaded[section])
            if "presets" in loaded and isinstance(loaded["presets"], list):
                merged["presets"] = loaded["presets"]

        # Environment variable overrides take highest precedence
        if os.environ.get("MOUNT_BASE"):
            merged["storage"]["mount_base"] = os.environ.get("MOUNT_BASE")
        if os.environ.get("CACHE_BASE"):
            merged["storage"]["cache_base"] = os.environ.get("CACHE_BASE")
        if os.environ.get("RCLONE_CONF_PATH"):
            merged["storage"]["rclone_conf_path"] = os.environ.get("RCLONE_CONF_PATH")
        if os.environ.get("RCLONE_RC_URL"):
            merged["storage"]["rclone_rc_url"] = os.environ.get("RCLONE_RC_URL")
        if os.environ.get("PRIMARY_REMOTE"):
            merged["storage"]["primary_remote"] = os.environ.get("PRIMARY_REMOTE")

        _cached_config = merged
        return _cached_config

def save_app_config(new_config):
    """Atomically saves application settings."""
    global _cached_config
    with STATE_LOCK:
        _cached_config = new_config
        return atomic_write_json(APP_CONFIG_PATH, new_config)

# Convenience Accessors
def get_primary_remote():
    cfg = get_app_config()
    rem = cfg.get("storage", {}).get("primary_remote", "bkc:").strip()
    if not rem.endswith(":"):
        rem += ":"
    return rem

def get_vfs_cache_max_gb():
    cfg = get_app_config()
    try:
        return float(cfg.get("storage", {}).get("vfs_cache_max_gb", 10.0))
    except (ValueError, TypeError):
        return 10.0

def get_mount_base():
    cfg = get_app_config()
    return cfg.get("storage", {}).get("mount_base", MOUNT_BASE)

def get_cache_base():
    cfg = get_app_config()
    return cfg.get("storage", {}).get("cache_base", CACHE_BASE)

def get_rclone_rc_url():
    cfg = get_app_config()
    return cfg.get("storage", {}).get("rclone_rc_url", RCLONE_RC_URL)

def get_rclone_conf_path():
    cfg = get_app_config()
    return cfg.get("storage", {}).get("rclone_conf_path", RCLONE_CONF_PATH)

def get_server_external_url():
    cfg = get_app_config()
    return cfg.get("general", {}).get("server_external_url", "").strip()

def get_worker_cdn_url():
    cfg = get_app_config()
    return cfg.get("general", {}).get("worker_cdn_url", "").strip()

def get_immich_web_url():
    cfg = get_app_config()
    return cfg.get("general", {}).get("immich_web_url", "").strip()

def get_rclone_gui_url():
    cfg = get_app_config()
    return cfg.get("general", {}).get("rclone_gui_url", "").strip()

def get_app_name():
    cfg = get_app_config()
    return cfg.get("general", {}).get("app_name", "Immich & Duplication Control Center").strip()

def get_presets():
    cfg = get_app_config()
    return cfg.get("presets", [])

def save_preset(preset_data):
    """Adds or updates a duplication preset."""
    with STATE_LOCK:
        cfg = get_app_config()
        presets = cfg.get("presets", [])
        pid = preset_data.get("id") or f"preset-{secrets.token_hex(3)}"
        preset_data["id"] = pid
        found = False
        for i, p in enumerate(presets):
            if p.get("id") == pid:
                presets[i] = preset_data
                found = True
                break
        if not found:
            presets.append(preset_data)
        cfg["presets"] = presets
        save_app_config(cfg)
        return preset_data

def delete_preset(preset_id):
    """Removes a duplication preset."""
    with STATE_LOCK:
        cfg = get_app_config()
        presets = cfg.get("presets", [])
        initial_len = len(presets)
        presets = [p for p in presets if p.get("id") != preset_id]
        if len(presets) != initial_len:
            cfg["presets"] = presets
            save_app_config(cfg)
            return True
        return False
