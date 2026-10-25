import os
import shutil
import time
import json
import threading
import urllib.request
from datetime import datetime
from dashboard.config import (
    get_mount_base,
    get_cache_base,
    get_rclone_conf_path,
    get_rclone_rc_url,
    get_primary_remote,
    get_vfs_cache_max_gb,
    get_version_metadata,
    SCAN_LOCK,
    STATE_LOCK,
    format_size
)
from dashboard.services.workers import get_all_workers
from dashboard.services.transactions import load_transactions
from dashboard.services.tailscale import load_tailscale_config, mask_secret
from dashboard.services.updater import get_update_status

_meta_cache = {
    "files": [],
    "cached_count": 0,
    "cloud_count": 0,
    "cached_bytes": 0,
    "last_scan": 0
}
_session_max_uploaded_bytes = 0

# Authoritative Cloud Quota Cache (Decoupled from 500ms SSE loop)
_quota_lock = threading.Lock()
_cloud_quota_cache = {
    "remote": None,
    "raw": {"total": 0, "used": 0, "free": 0, "trashed": 0},
    "data": {
        "remote": "",
        "total": "0 B",
        "used": "0 B",
        "free": "0 B",
        "trashed": "0 B",
        "percent_used": 0.0
    },
    "last_updated": 0,
    "is_updating": False
}

def get_available_remotes():
    """Parses available remotes from rclone.conf or falls back to empty list."""
    remotes = []
    conf_path = get_rclone_conf_path()
    if os.path.exists(conf_path):
        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        name = line[1:-1]
                        remotes.append(f"{name}:")
        except Exception as e:
            print(f"[!] Error reading rclone config: {e}")
    return remotes

def query_rclone(endpoint, payload=None, timeout=0.3):
    """Sends a JSON query to the configured Rclone RC instance."""
    rc_base = get_rclone_rc_url().rstrip('/')
    url = f"{rc_base}/{endpoint}"
    data = json.dumps(payload).encode() if payload else b"{}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except:
        return None

def fetch_cloud_quota(remote, timeout=5.0):
    """
    Directly queries operations/about via Rclone RC with non-destructive semantics.
    Supports crypt and alias remotes with fallback to underlying drive if needed.
    """
    if not remote:
        return {
            "remote": "",
            "total": "0 B",
            "used": "0 B",
            "free": "0 B",
            "trashed": "0 B",
            "percent_used": 0.0,
            "raw": {"total": 0, "used": 0, "free": 0, "trashed": 0}
        }

    rem_param = remote if remote.endswith(":") else f"{remote}:"
    cloud_info = query_rclone("operations/about", {"fs": rem_param}, timeout=timeout)

    # Fallback to underlying remote if crypt/alias failed or returned empty
    if not cloud_info:
        try:
            from dashboard.services.transactions import resolve_remote_info
            info = resolve_remote_info(remote.rstrip(":"))
            underlying = info.get("underlying")
            if underlying and underlying != remote.rstrip(":"):
                cloud_info = query_rclone("operations/about", {"fs": f"{underlying}:"}, timeout=timeout)
        except Exception:
            pass

    cloud_info = cloud_info or {}
    cloud_total = cloud_info.get("total", 0) or 0
    cloud_used = cloud_info.get("used", 0) or 0
    cloud_free = cloud_info.get("free", 0) or 0
    cloud_trashed = cloud_info.get("trashed", 0) or 0
    pct = round((cloud_used / cloud_total) * 100, 1) if cloud_total > 0 else 0.0

    return {
        "remote": rem_param,
        "total": format_size(cloud_total),
        "used": format_size(cloud_used),
        "free": format_size(cloud_free),
        "trashed": format_size(cloud_trashed),
        "percent_used": pct,
        "raw": {
            "total": cloud_total,
            "used": cloud_used,
            "free": cloud_free,
            "trashed": cloud_trashed
        }
    }

def _async_quota_worker(remote, timeout=5.0):
    global _cloud_quota_cache
    try:
        quota = fetch_cloud_quota(remote, timeout=timeout)
        with _quota_lock:
            # Only update if we received valid quota or uninitialized
            if quota.get("raw", {}).get("total", 0) > 0 or _cloud_quota_cache["last_updated"] == 0:
                _cloud_quota_cache["remote"] = remote
                _cloud_quota_cache["raw"] = quota.get("raw", {})
                _cloud_quota_cache["data"] = {
                    "remote": remote,
                    "total": quota["total"],
                    "used": quota["used"],
                    "free": quota["free"],
                    "trashed": quota["trashed"],
                    "percent_used": quota["percent_used"]
                }
                _cloud_quota_cache["last_updated"] = time.time()
    except Exception as e:
        print(f"[!] Background cloud quota refresh error for {remote}: {e}")
    finally:
        with _quota_lock:
            _cloud_quota_cache["is_updating"] = False

def get_cached_cloud_quota(remote=None, max_age=120, force_refresh=False, allow_blocking_initial=False):
    """
    Returns authoritative primary cloud quota cached for max_age seconds.
    Non-blocking: Spawns an asynchronous background thread for cache replenishment
    to ensure the 500ms SSE loop is never delayed by 2-4s remote API calls.
    """
    global _cloud_quota_cache
    if remote is None:
        remote = get_primary_remote()

    if not remote:
        return {
            "remote": "",
            "total": "0 B",
            "used": "0 B",
            "free": "0 B",
            "trashed": "0 B",
            "percent_used": 0.0
        }

    now = time.time()
    needs_refresh = (
        force_refresh or
        _cloud_quota_cache["remote"] != remote or
        (now - _cloud_quota_cache["last_updated"] > max_age)
    )

    if needs_refresh:
        if force_refresh or (allow_blocking_initial and _cloud_quota_cache["last_updated"] == 0):
            with _quota_lock:
                _cloud_quota_cache["is_updating"] = True
            _async_quota_worker(remote, timeout=5.0)
        else:
            with _quota_lock:
                if not _cloud_quota_cache["is_updating"]:
                    _cloud_quota_cache["is_updating"] = True
                    t = threading.Thread(target=_async_quota_worker, args=(remote, 5.0), daemon=True)
                    t.start()

    with _quota_lock:
        res = dict(_cloud_quota_cache["data"])
        if not res.get("remote"):
            res["remote"] = remote
        return res

def scan_files_if_needed():
    """Scans local SSD VFS cache and mount point, cached for 10 seconds under SCAN_LOCK."""
    global _meta_cache
    now = time.time()
    if now - _meta_cache["last_scan"] < 10 and _meta_cache["files"]:
        return

    mount_path = get_mount_base()
    cache_path = get_cache_base()

    with SCAN_LOCK:
        if now - _meta_cache["last_scan"] < 10 and _meta_cache["files"]:
            return

        cached_paths = set()
        cached_bytes = 0
        if os.path.exists(cache_path):
            for root, _, files in os.walk(cache_path):
                for f in files:
                    if f.startswith("."): continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, cache_path)
                    cached_paths.add(rel_path)
                    try:
                        cached_bytes += os.path.getsize(full_path)
                    except:
                        pass

        file_list = []
        if os.path.exists(mount_path):
            for root, _, files in os.walk(mount_path):
                for f in files:
                    if f.startswith("."): continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, mount_path)
                    try:
                        sz = os.path.getsize(full_path)
                        mtime = os.path.getmtime(full_path)
                        mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                    except:
                        sz = 0
                        mtime_str = "-"

                    is_cached = rel_path in cached_paths
                    file_list.append({
                        "name": f,
                        "path": rel_path,
                        "size": format_size(sz),
                        "size_bytes": sz,
                        "cached": is_cached,
                        "mtime": mtime_str
                    })

        file_list.sort(key=lambda x: x["path"], reverse=True)
        cached_count = len([x for x in file_list if x["cached"]])
        cloud_count = len(file_list) - cached_count

        _meta_cache = {
            "files": file_list,
            "cached_count": cached_count,
            "cloud_count": cloud_count,
            "cached_bytes": cached_bytes,
            "last_scan": now
        }

def get_paginated_media(page=1, limit=50, filter_type="all", search_query=""):
    """Returns paginated media files from cache."""
    scan_files_if_needed()
    all_files = _meta_cache["files"]
    q = search_query.lower()
    filtered = []
    for f in all_files:
        if q and not (q in f["name"].lower() or q in f["path"].lower()):
            continue
        if filter_type == "cached" and not f["cached"]:
            continue
        if filter_type == "cloud" and f["cached"]:
            continue
        filtered.append(f)

    total_filtered = len(filtered)
    total_pages = max(1, (total_filtered + limit - 1) // limit)
    page = max(1, min(page, total_pages))
    start = (page - 1) * limit
    end = start + limit

    return {
        "page": page,
        "limit": limit,
        "total_files": total_filtered,
        "total_pages": total_pages,
        "files": filtered[start:end]
    }

def get_live_sse_payload():
    """Generates the unified 500ms telemetry SSE payload."""
    scan_files_if_needed()

    try:
        disk = shutil.disk_usage("/")
        disk_free = disk.free
        disk_used = disk.used
        disk_total = disk.total
    except:
        disk_free = disk_used = disk_total = 0

    global _session_max_uploaded_bytes
    rc_stats = query_rclone("core/stats")
    vfs_stats = query_rclone("vfs/stats")
    transferred_resp = query_rclone("core/transferred")
    bw_info = query_rclone("core/bwlimit")

    active_transfers = []
    speed_str = "0 B/s"
    live_speed = 0
    total_uploaded_str = "0 B"
    transfers_done = 0
    transfers_failed = 0
    transfers_in_progress = 0
    uploads_queued = 0
    remaining_bytes = 0

    if rc_stats:
        current_rc_bytes = rc_stats.get("bytes", 0)
        if current_rc_bytes > _session_max_uploaded_bytes:
            _session_max_uploaded_bytes = current_rc_bytes
        total_uploaded_str = format_size(_session_max_uploaded_bytes)
        transfers_done = rc_stats.get("transfers", 0)
        transfers_failed = rc_stats.get("errors", 0)
        raw_transferring = rc_stats.get("transferring", []) or []
        transfers_in_progress = len(raw_transferring)
        live_speed = sum(t.get("speed", 0) for t in raw_transferring)
        speed_str = f"{format_size(live_speed)}/s" if raw_transferring else "0 B/s"
        remaining_bytes = sum(max(0, t.get("size", 0) - t.get("bytes", 0)) for t in raw_transferring)

        for t in raw_transferring:
            active_transfers.append({
                "name": t.get("name", ""),
                "size": format_size(t.get("size", 0)),
                "bytes": format_size(t.get("bytes", 0)),
                "percentage": t.get("percentage", 0),
                "speed": f"{format_size(t.get('speed', 0))}/s",
                "eta": t.get("eta", 0)
            })

    if vfs_stats and isinstance(vfs_stats, dict):
        disk_cache = vfs_stats.get("diskCache", {})
        uploads_queued = disk_cache.get("uploadsQueued", 0)

    recent_transfers = []
    failed_transfers = []
    if transferred_resp and isinstance(transferred_resp, dict) and "transferred" in transferred_resp:
        all_transferred = transferred_resp.get("transferred", []) or []
        for item in reversed(all_transferred):
            err = item.get("error", "")
            rec = {
                "name": item.get("name", ""),
                "size": format_size(item.get("size", 0)),
                "bytes": format_size(item.get("bytes", 0)),
                "completed_at": item.get("completed_at", ""),
                "error": err,
                "failed": bool(err)
            }
            if err:
                if len(failed_transfers) < 25:
                    failed_transfers.append(rec)
            else:
                if len(recent_transfers) < 30:
                    recent_transfers.append(rec)

    bw_rate = bw_info.get("rate", "off") if bw_info else "off"
    is_paused = (bw_rate in ("1B", "0"))

    # Non-blocking Authoritative Cloud Quota (120s TTL cache with background updater)
    primary_rem = get_primary_remote()
    primary_cloud_data = get_cached_cloud_quota(primary_rem, max_age=120)

    cached_bytes = _meta_cache["cached_bytes"]
    cached_count = _meta_cache["cached_count"]
    cloud_count = _meta_cache["cloud_count"]
    total_count = len(_meta_cache["files"])

    # Dynamic VFS cache limit calculation
    vfs_limit_gb = get_vfs_cache_max_gb()
    vfs_limit_bytes = vfs_limit_gb * (1024 ** 3)
    cache_limit_str = f"{vfs_limit_gb:.1f} GB"
    cache_percent = round((cached_bytes / vfs_limit_bytes) * 100, 1) if vfs_limit_bytes > 0 else 0

    with STATE_LOCK:
        tx_list = load_transactions()
        workers_list = get_all_workers()
        ts_cfg = load_tailscale_config()
        ts_status = {
            "configured": bool(ts_cfg.get("auth_key") or ts_cfg.get("api_key") or (ts_cfg.get("oauth_client_id") and ts_cfg.get("oauth_client_secret"))),
            "mode": ts_cfg.get("mode", "auth_key"),
            "masked_key": mask_secret(ts_cfg.get("auth_key", "")),
            "masked_api": mask_secret(ts_cfg.get("api_key", "")),
            "tailnet": ts_cfg.get("tailnet", ""),
            "auto_inject": ts_cfg.get("auto_inject", True),
            "ephemeral": ts_cfg.get("ephemeral", True)
        }

    return {
        "summary": {
            "total_files": total_count,
            "cached_files": cached_count,
            "cloud_files": cloud_count,
            "cached_size": format_size(cached_bytes),
            "cached_bytes": cached_bytes,
            "cache_limit": cache_limit_str,
            "cache_percent": cache_percent,
            "disk_free": format_size(disk_free),
            "disk_total": format_size(disk_total)
        },
        "storage": {
            "local_ssd": {
                "total": format_size(disk_total),
                "used": format_size(disk_used),
                "free": format_size(disk_free),
                "percent_used": round((disk_used / disk_total) * 100, 1) if disk_total else 0,
                "vfs_cache_used": format_size(cached_bytes),
                "vfs_cache_limit": cache_limit_str,
                "vfs_cache_percent": cache_percent
            },
            "primary_cloud": primary_cloud_data
        },
        "rclone": {
            "speed": speed_str,
            "speed_bps": live_speed,
            "total_uploaded": total_uploaded_str,
            "total_uploaded_bytes": _session_max_uploaded_bytes,
            "transfers_done": transfers_done,
            "transfers_failed": transfers_failed,
            "transfers_active": transfers_in_progress,
            "uploads_queued": uploads_queued,
            "remaining_bytes_str": format_size(remaining_bytes),
            "is_paused": is_paused,
            "bw_rate": bw_rate,
            "jobs": active_transfers,
            "recent_transfers": recent_transfers,
            "failed_transfers": failed_transfers
        },
        "transactions": tx_list,
        "workers": workers_list,
        "tailscale": ts_status,
        "version": get_version_metadata(),
        "updates": get_update_status()
    }
