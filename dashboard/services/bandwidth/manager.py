import os
import json
import time
import threading
from typing import Dict, Any, Optional

from dashboard.config import (
    STATE_LOCK,
    BANDWIDTH_CONF_PATH,
    atomic_write_json,
    format_size
)
from dashboard.services.bandwidth.base import BaseISPProvider, BandwidthSnapshot
from dashboard.services.bandwidth.providers import get_provider_classes

DEFAULT_BANDWIDTH_CONFIG = {
    "enabled": True,
    "active_provider": "biznet",
    "poll_interval_seconds": 300,
    "warning_threshold_pct": 20.0,
    "critical_threshold_pct": 10.0,
    "providers": {
        "biznet": {
            "biznet_id": "",
            "username": "",
            "password": ""
        },
        "manual": {
            "plan_speed_mbps": 100.0,
            "monthly_quota_gb": 1000.0,
            "quota_remaining_gb": 450.0,
            "reset_day_of_month": 1,
            "last_downtime_reason": "Dying-gasp",
            "last_downtime_sub": "Power loss detected by OLT"
        }
    }
}

# Singleton instances cache to preserve in-memory session tokens
_INSTANCES: Dict[str, BaseISPProvider] = {}
_INSTANCES_LOCK = threading.Lock()

# Snapshot and polling state
_cached_snapshot: Optional[BandwidthSnapshot] = None
_last_fetch_time: float = 0.0
_is_fetching: bool = False
_fetch_lock = threading.Lock()

def get_provider_instance(provider_id: str) -> BaseISPProvider:
    """Returns persistent singleton instance for the requested provider."""
    with _INSTANCES_LOCK:
        if provider_id not in _INSTANCES:
            classes = get_provider_classes()
            cls = classes.get(provider_id)
            if not cls:
                cls = classes.get("manual")
            _INSTANCES[provider_id] = cls()
        return _INSTANCES[provider_id]

def load_bandwidth_config() -> Dict[str, Any]:
    """Loads bandwidth configuration with schema merging."""
    with STATE_LOCK:
        cfg = json.loads(json.dumps(DEFAULT_BANDWIDTH_CONFIG))
        if os.path.exists(BANDWIDTH_CONF_PATH):
            try:
                with open(BANDWIDTH_CONF_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        for k, v in loaded.items():
                            if k == "providers" and isinstance(v, dict):
                                for p_k, p_v in v.items():
                                    if p_k in cfg["providers"] and isinstance(p_v, dict):
                                        cfg["providers"][p_k].update(p_v)
                                    else:
                                        cfg["providers"][p_k] = p_v
                            else:
                                cfg[k] = v
            except Exception as e:
                print(f"[!] Error loading bandwidth config from {BANDWIDTH_CONF_PATH}: {e}")
        return cfg

def save_bandwidth_config(new_config: Dict[str, Any]) -> bool:
    """Saves bandwidth configuration, preserving existing password if masked."""
    with STATE_LOCK:
        current = load_bandwidth_config()
        # Preserve masked passwords if client sent placeholder
        providers = new_config.get("providers", {})
        for p_id, p_creds in providers.items():
            if isinstance(p_creds, dict):
                cur_creds = current.get("providers", {}).get(p_id, {})
                for field in ("password", "api_token", "secret"):
                    val = str(p_creds.get(field, "")).strip()
                    if val in ("••••••••", "********", "") and cur_creds.get(field):
                        p_creds[field] = cur_creds[field]

        success = atomic_write_json(BANDWIDTH_CONF_PATH, new_config)
        if success:
            # Trigger immediate background re-fetch with new config
            trigger_fetch(force=True)
        return success

def mask_bandwidth_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Creates a sanitized copy of configuration with credentials masked."""
    clean = json.loads(json.dumps(cfg))
    providers = clean.get("providers", {})
    for p_id, p_creds in providers.items():
        if isinstance(p_creds, dict):
            for field in ("password", "api_token", "secret"):
                if p_creds.get(field):
                    p_creds[field] = "••••••••"
    return clean

def _perform_fetch():
    global _cached_snapshot, _last_fetch_time, _is_fetching
    try:
        cfg = load_bandwidth_config()
        if not cfg.get("enabled", True):
            return

        active_id = cfg.get("active_provider", "biznet")
        provider = get_provider_instance(active_id)
        creds = cfg.get("providers", {}).get(active_id, {})
        snapshot = provider.fetch_telemetry(creds)
        _cached_snapshot = snapshot
        _last_fetch_time = time.time()
    except Exception as e:
        print(f"[!] Bandwidth refresh error: {e}")
    finally:
        _is_fetching = False

def trigger_fetch(force: bool = False):
    """Spawns an asynchronous background thread to refresh bandwidth snapshot."""
    global _is_fetching
    with _fetch_lock:
        if _is_fetching:
            return
        cfg = load_bandwidth_config()
        poll_interval = float(cfg.get("poll_interval_seconds", 300))
        if force or (time.time() - _last_fetch_time > poll_interval):
            _is_fetching = True
            t = threading.Thread(target=_perform_fetch, daemon=True)
            t.start()

def test_provider_connection(provider_id: Optional[str] = None, credentials: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Tests a provider synchronously and returns structured diagnostics."""
    cfg = load_bandwidth_config()
    target_id = provider_id or cfg.get("active_provider", "biznet")
    provider = get_provider_instance(target_id)

    creds = credentials if credentials is not None else cfg.get("providers", {}).get(target_id, {})
    # Unmask password if placeholder was passed
    cur_creds = cfg.get("providers", {}).get(target_id, {})
    for field in ("password", "api_token", "secret"):
        if creds.get(field) in ("••••••••", "********", "") and cur_creds.get(field):
            creds[field] = cur_creds[field]

    start_t = time.time()
    snapshot = provider.fetch_telemetry(creds)
    latency_ms = round((time.time() - start_t) * 1000, 1)

    return {
        "success": snapshot.online,
        "provider_id": snapshot.provider_id,
        "provider_name": snapshot.provider_name,
        "latency_ms": latency_ms,
        "plan_speed_mbps": snapshot.plan_speed_mbps,
        "quota_remaining_bytes": snapshot.quota_remaining_bytes,
        "quota_remaining_str": format_size(snapshot.quota_remaining_bytes),
        "quota_limit_bytes": snapshot.quota_limit_bytes,
        "quota_limit_str": format_size(snapshot.quota_limit_bytes),
        "reset_timestamp": snapshot.reset_timestamp,
        "last_downtime_reason": snapshot.last_downtime_reason,
        "last_downtime_sub": snapshot.last_downtime_sub,
        "error_message": snapshot.error_message
    }

def get_cached_bandwidth_status(live_upload_bps: float = 0.0) -> Dict[str, Any]:
    """
    Sub-millisecond non-blocking call for SSE loop.
    Returns current cached snapshot combined with real-time saturation.
    Spawns background refresh when stale.
    """
    global _cached_snapshot
    trigger_fetch(force=False)

    snapshot = _cached_snapshot
    if not snapshot:
        # Initial default fallback snapshot
        cfg = load_bandwidth_config()
        active_id = cfg.get("active_provider", "manual")
        provider = get_provider_instance(active_id)
        creds = cfg.get("providers", {}).get(active_id, {})
        snapshot = provider.fetch_telemetry(creds)

    # Real-time saturation calculation
    plan_mbps = max(1.0, float(snapshot.plan_speed_mbps or 100.0))
    live_mbps = (live_upload_bps * 8.0) / 1_000_000.0
    saturation_pct = min(100.0, round((live_mbps / plan_mbps) * 100.0, 1))

    rem_bytes = snapshot.quota_remaining_bytes
    lim_bytes = snapshot.quota_limit_bytes
    used_bytes = max(0, lim_bytes - rem_bytes)
    rem_pct = round((rem_bytes / lim_bytes) * 100.0, 1) if lim_bytes > 0 else 0.0
    used_pct = round((used_bytes / lim_bytes) * 100.0, 1) if lim_bytes > 0 else 0.0

    days_left = max(0, int((snapshot.reset_timestamp - time.time()) / 86400)) if snapshot.reset_timestamp else 0

    return {
        "provider_id": snapshot.provider_id,
        "provider_name": snapshot.provider_name,
        "online": snapshot.online,
        "plan_speed_mbps": plan_mbps,
        "plan_speed_str": f"{int(plan_mbps)} Mbps",
        "live_speed_bps": live_upload_bps,
        "live_speed_str": f"{format_size(live_upload_bps)}/s",
        "live_speed_mbps": round(live_mbps, 2),
        "saturation_pct": saturation_pct,
        "quota": {
            "remaining_bytes": rem_bytes,
            "remaining_str": format_size(rem_bytes),
            "limit_bytes": lim_bytes,
            "limit_str": format_size(lim_bytes),
            "used_bytes": used_bytes,
            "used_str": format_size(used_bytes),
            "remaining_pct": rem_pct,
            "used_pct": used_pct,
            "reset_timestamp": snapshot.reset_timestamp,
            "days_left": days_left
        },
        "downtime": {
            "reason": snapshot.last_downtime_reason or "Normal",
            "subtext": snapshot.last_downtime_sub or "No downtime detected"
        },
        "last_updated": snapshot.fetched_at,
        "error_message": snapshot.error_message
    }

def format_prometheus_metrics() -> str:
    """Exposes authoritative Prometheus metrics directly from in-memory cache."""
    status = get_cached_bandwidth_status(0.0)
    quota = status.get("quota", {})
    downtime = status.get("downtime", {})
    provider_id = status.get("provider_id", "unknown")

    lines = [
        f'# HELP immiclone_bandwidth_plan_speed_mbps ISP plan speed in Mbps',
        f'# TYPE immiclone_bandwidth_plan_speed_mbps gauge',
        f'immiclone_bandwidth_plan_speed_mbps{{provider="{provider_id}"}} {status.get("plan_speed_mbps", 0)}',
        f'# HELP immiclone_bandwidth_quota_remaining_bytes Monthly remaining data quota in bytes',
        f'# TYPE immiclone_bandwidth_quota_remaining_bytes gauge',
        f'immiclone_bandwidth_quota_remaining_bytes{{provider="{provider_id}"}} {quota.get("remaining_bytes", 0)}',
        f'# HELP immiclone_bandwidth_quota_limit_bytes Monthly total data quota limit in bytes',
        f'# TYPE immiclone_bandwidth_quota_limit_bytes gauge',
        f'immiclone_bandwidth_quota_limit_bytes{{provider="{provider_id}"}} {quota.get("limit_bytes", 0)}',
        f'# HELP immiclone_bandwidth_quota_valid_until Quota renewal timestamp in unix epoch',
        f'# TYPE immiclone_bandwidth_quota_valid_until gauge',
        f'immiclone_bandwidth_quota_valid_until{{provider="{provider_id}"}} {quota.get("reset_timestamp", 0)}',
        f'# HELP immiclone_bandwidth_online Provider API and connection health status (1=online, 0=offline)',
        f'# TYPE immiclone_bandwidth_online gauge',
        f'immiclone_bandwidth_online{{provider="{provider_id}"}} {1 if status.get("online") else 0}',
        f'# HELP immiclone_bandwidth_downtime_info Last known downtime event with reason labels',
        f'# TYPE immiclone_bandwidth_downtime_info gauge',
        f'immiclone_bandwidth_downtime_info{{provider="{provider_id}",reason="{downtime.get("reason", "")}"}} 1',
    ]
    return "\n".join(lines) + "\n"
