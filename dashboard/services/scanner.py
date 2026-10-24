import os
import shutil
import time
import json
import urllib.request
from datetime import datetime
from dashboard.config import (
    MOUNT_BASE,
    CACHE_BASE,
    RCLONE_CONF_PATH,
    SCAN_LOCK,
    STATE_LOCK,
    format_size
)
from dashboard.services.workers import get_all_workers
from dashboard.services.transactions import load_transactions
from dashboard.services.tailscale import load_tailscale_config, mask_secret

_meta_cache = {
    "files": [],
    "cached_count": 0,
    "cloud_count": 0,
    "cached_bytes": 0,
    "last_scan": 0
}

def get_available_remotes():
    """Parses available remotes from rclone.conf."""
    remotes = []
    if os.path.exists(RCLONE_CONF_PATH):
        try:
            with open(RCLONE_CONF_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        name = line[1:-1]
                        remotes.append(f"{name}:")
        except Exception as e:
            print(f"[!] Error reading rclone config: {e}")
    return remotes

def query_rclone(endpoint, payload=None):
    """Sends a JSON query to the local Rclone RC instance on port 5572."""
    url = f"http://localhost:5572/{endpoint}"
    data = json.dumps(payload).encode() if payload else b"{}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return json.loads(resp.read().decode())
    except:
        return None

def scan_files_if_needed():
    """Scans local SSD VFS cache and mount point, cached for 10 seconds under SCAN_LOCK."""
    global _meta_cache
    now = time.time()
    if now - _meta_cache["last_scan"] < 10 and _meta_cache["files"]:
        return

    with SCAN_LOCK:
        if now - _meta_cache["last_scan"] < 10 and _meta_cache["files"]:
            return

        cached_paths = set()
        cached_bytes = 0
        if os.path.exists(CACHE_BASE):
            for root, _, files in os.walk(CACHE_BASE):
                for f in files:
                    if f.startswith("."): continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, CACHE_BASE)
                    cached_paths.add(rel_path)
                    try:
                        cached_bytes += os.path.getsize(full_path)
                    except:
                        pass

        file_list = []
        if os.path.exists(MOUNT_BASE):
            for root, _, files in os.walk(MOUNT_BASE):
                for f in files:
                    if f.startswith("."): continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, MOUNT_BASE)
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

    rc_stats = query_rclone("core/stats")
    active_transfers = []
    speed_str = "0 B/s"
    total_uploaded_str = "0 B"
    transfers_done = 0
    transfers_in_progress = 0

    if rc_stats:
        total_uploaded_str = format_size(rc_stats.get("bytes", 0))
        transfers_done = rc_stats.get("transfers", 0)
        raw_transferring = rc_stats.get("transferring", []) or []
        transfers_in_progress = len(raw_transferring)
        live_speed = sum(t.get("speed", 0) for t in raw_transferring)
        speed_str = f"{format_size(live_speed)}/s" if raw_transferring else "0 B/s"

        for t in raw_transferring:
            active_transfers.append({
                "name": t.get("name", ""),
                "size": format_size(t.get("size", 0)),
                "bytes": format_size(t.get("bytes", 0)),
                "percentage": t.get("percentage", 0),
                "speed": f"{format_size(t.get('speed', 0))}/s",
                "eta": t.get("eta", 0)
            })

    cloud_info = query_rclone("operations/about", {"fs": "bkc:"}) or {}
    cloud_total = cloud_info.get("total", 0)
    cloud_used = cloud_info.get("used", 0)
    cloud_free = cloud_info.get("free", 0)
    cloud_trashed = cloud_info.get("trashed", 0)

    cached_bytes = _meta_cache["cached_bytes"]
    cached_count = _meta_cache["cached_count"]
    cloud_count = _meta_cache["cloud_count"]
    total_count = len(_meta_cache["files"])

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
            "cache_limit": "10.0 GB",
            "cache_percent": round((cached_bytes / (10 * 1024**3)) * 100, 1),
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
                "vfs_cache_limit": "10.0 GB",
                "vfs_cache_percent": round((cached_bytes / (10 * 1024**3)) * 100, 1)
            },
            "cloud_bkc": {
                "total": format_size(cloud_total),
                "used": format_size(cloud_used),
                "free": format_size(cloud_free),
                "trashed": format_size(cloud_trashed),
                "percent_used": round((cloud_used / cloud_total) * 100, 1) if cloud_total else 0
            }
        },
        "rclone": {
            "speed": speed_str,
            "total_uploaded": total_uploaded_str,
            "transfers_done": transfers_done,
            "transfers_active": transfers_in_progress,
            "jobs": active_transfers
        },
        "transactions": tx_list,
        "workers": workers_list,
        "tailscale": ts_status
    }
