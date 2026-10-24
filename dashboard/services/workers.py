import os
import json
import time
import secrets
from dashboard.config import (
    APP_VERSION,
    WORKERS_STORE_PATH,
    STATE_LOCK,
    atomic_write_json,
    get_server_external_url,
    get_worker_cdn_url
)
from dashboard.services.tailscale import get_effective_tailscale_key

# In-memory worker lookup cache (synchronized with WORKERS_STORE_PATH)
_active_workers = {} # worker_id -> { id, name, token, hostname, status, last_seen, current_tx, lease_id, notes, created_at, pending_action }
_worker_tokens = {}  # token -> worker_id

def load_workers():
    """Loads workers from disk."""
    with STATE_LOCK:
        if os.path.exists(WORKERS_STORE_PATH):
            try:
                with open(WORKERS_STORE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Error loading workers: {e}")
        return []

def save_workers_list(workers_list):
    """Saves workers to disk atomically."""
    with STATE_LOCK:
        return atomic_write_json(WORKERS_STORE_PATH, workers_list)

def init_workers_from_disk():
    """Initializes in-memory worker table on server startup."""
    global _active_workers, _worker_tokens
    with STATE_LOCK:
        stored = load_workers()
        for w in stored:
            wid = w.get("id")
            if wid:
                if time.time() - w.get("last_seen", 0) > 15:
                    w["status"] = "OFFLINE"
                _active_workers[wid] = w
                if w.get("token"):
                    _worker_tokens[w["token"]] = wid

def sync_workers_to_disk():
    """Syncs in-memory table to disk."""
    with STATE_LOCK:
        save_workers_list(list(_active_workers.values()))

def get_worker(wid):
    """Gets a worker dictionary by ID."""
    with STATE_LOCK:
        return _active_workers.get(wid)

def get_all_workers():
    """Returns a list of all workers with live telemetry."""
    with STATE_LOCK:
        return [
            {
                "id": w["id"],
                "name": w.get("name", w["id"]),
                "hostname": w.get("hostname", "unknown"),
                "version": w.get("version", APP_VERSION),
                "version_match": (w.get("version") == APP_VERSION if w.get("version") else True),
                "status": w.get("status", "STANDBY"),
                "current_tx": w.get("current_tx"),
                "notes": w.get("notes", ""),
                "created_at": w.get("created_at", int(time.time())),
                "last_seen_sec": int(time.time() - w.get("last_seen", 0))
            }
            for w in _active_workers.values()
        ]

def get_active_workers_dict():
    """Returns the internal active workers dictionary."""
    return _active_workers

def verify_worker_token(wid, token):
    """Verifies that a worker token matches."""
    with STATE_LOCK:
        worker = _active_workers.get(wid)
        return bool(worker and worker.get("token") == token)

def create_worker_session(name=None, notes=None, include_tailscale=True, request_host=None, force_fresh=False):
    """Pre-provisions a worker session and generates the ready-to-use one-liner command."""
    wid = f"worker-{secrets.token_hex(2)}"
    tok = secrets.token_urlsafe(16)
    friendly_name = name or f"Cloud Shell {wid}"
    worker_notes = notes or "Ephemeral cloud runner"

    with STATE_LOCK:
        _active_workers[wid] = {
            "id": wid,
            "name": friendly_name,
            "token": tok,
            "hostname": "Pending connection...",
            "status": "STANDBY",
            "last_seen": time.time(),
            "current_tx": None,
            "notes": worker_notes,
            "created_at": int(time.time()),
            "pending_action": None
        }
        _worker_tokens[tok] = wid
        sync_workers_to_disk()

    ts_flag = ""
    ts_warning = None
    if include_tailscale:
        effective_ts = get_effective_tailscale_key(force_fresh=force_fresh)
        if effective_ts:
            ts_flag = f" --tailscale-key {effective_ts}"
        else:
            ts_warning = "Could not generate an active Tailscale auth key. Please verify your Tailscale API Key or Auth Key in settings."

    # Determine server endpoint: configured external URL > Host header > fallback
    configured_url = get_server_external_url()
    if configured_url:
        endpoint = configured_url.rstrip('/')
    elif request_host:
        endpoint = f"http://{request_host}"
    else:
        endpoint = "http://localhost:8080"

    # Determine script URL: configured CDN > default stable runner on GitHub
    cdn_url = get_worker_cdn_url()
    if cdn_url:
        script_url = cdn_url
    else:
        script_url = "https://raw.githubusercontent.com/BoredKevin/immiclone/refs/heads/main/worker/worker-stable.sh"

    one_liner = f"curl -sSL {script_url} | bash -s -- --id {wid} --endpoint {endpoint} --token {tok}{ts_flag}"
    resp = {
        "worker_id": wid,
        "token": tok,
        "one_liner": one_liner
    }
    if ts_warning:
        resp["warning"] = ts_warning
    return resp

def create_custom_worker(name, notes=""):
    """Pre-registers a worker with custom friendly metadata."""
    wid = f"worker-{secrets.token_hex(2)}"
    tok = secrets.token_urlsafe(16)
    with STATE_LOCK:
        _active_workers[wid] = {
            "id": wid,
            "name": name or f"Worker {wid}",
            "token": tok,
            "hostname": "Pending connection...",
            "version": APP_VERSION,
            "status": "STANDBY",
            "last_seen": time.time(),
            "current_tx": None,
            "notes": notes,
            "created_at": int(time.time()),
            "pending_action": None
        }
        _worker_tokens[tok] = wid
        sync_workers_to_disk()
    return wid

def register_worker(wid, hostname="unknown", version=None):
    """Registers or updates a worker handshake on connection."""
    with STATE_LOCK:
        if wid not in _active_workers:
            _active_workers[wid] = {
                "id": wid,
                "name": f"Worker {wid}",
                "token": "",
                "hostname": hostname,
                "version": version or APP_VERSION,
                "status": "STANDBY",
                "last_seen": time.time(),
                "current_tx": None,
                "notes": "Self-registered runner",
                "created_at": int(time.time()),
                "pending_action": None
            }
        else:
            _active_workers[wid]["hostname"] = hostname
            if version:
                _active_workers[wid]["version"] = version
            _active_workers[wid]["status"] = "STANDBY"
            _active_workers[wid]["last_seen"] = time.time()
        sync_workers_to_disk()

def update_worker(wid, updates):
    """Updates worker metadata (e.g. name, notes)."""
    with STATE_LOCK:
        if wid in _active_workers:
            for k, v in updates.items():
                if k in ("name", "notes", "status", "current_tx", "pending_action", "last_seen"):
                    _active_workers[wid][k] = v
            sync_workers_to_disk()
            return True
        return False

def disconnect_worker(wid):
    """Signals worker to terminate."""
    with STATE_LOCK:
        if wid in _active_workers:
            _active_workers[wid]["pending_action"] = "STOP"
            _active_workers[wid]["status"] = "OFFLINE"
            sync_workers_to_disk()
            return True
        return False

def reset_worker(wid):
    """Resets worker status to STANDBY."""
    with STATE_LOCK:
        if wid in _active_workers:
            _active_workers[wid]["status"] = "STANDBY"
            _active_workers[wid]["current_tx"] = None
            _active_workers[wid]["pending_action"] = None
            _active_workers[wid]["last_seen"] = time.time()
            sync_workers_to_disk()
            return True
        return False

def delete_worker(wid):
    """Removes a worker from the registry."""
    with STATE_LOCK:
        if wid in _active_workers:
            tok = _active_workers[wid].get("token")
            if tok and tok in _worker_tokens:
                del _worker_tokens[tok]
            del _active_workers[wid]
            sync_workers_to_disk()
            return True
        return False

def prune_offline_workers():
    """Removes all offline workers in bulk."""
    with STATE_LOCK:
        removed = 0
        for wid in list(_active_workers.keys()):
            if _active_workers[wid].get("status") == "OFFLINE":
                delete_worker(wid)
                removed += 1
        return removed
