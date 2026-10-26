import os
import json
import time
import secrets
import configparser
from datetime import datetime
from dashboard.config import (
    TX_STORE_PATH,
    STATE_LOCK,
    atomic_write_json,
    format_size,
    get_primary_remote,
    get_rclone_conf_path
)

DEFAULT_RCLONE_FLAGS = [
    "--size-only",
    "--drive-chunk-size=64M",
    "--drive-upload-cutoff=64M",
    "--buffer-size=32M",
    "--transfers=4",
    "--checkers=8",
    "--tpslimit=10",
    "--drive-pacer-min-sleep=10ms"
]

def parse_remote_name(path):
    """Extracts remote name from a remote path string, e.g. 'bkc:photos' -> 'bkc'."""
    if not path or not isinstance(path, str):
        return ""
    if ":" in path:
        return path.split(":")[0].strip()
    return ""

def resolve_remote_info(remote_name):
    """
    Parses rclone.conf to determine remote type and underlying remote.
    Resolves crypt/alias chains, e.g. bkc -> boredkevinmedia.
    """
    clean_name = remote_name.rstrip(":")
    if not clean_name:
        return {"remote": "", "type": "local", "underlying": "", "account_id": ""}

    conf_path = get_rclone_conf_path()
    if not os.path.exists(conf_path):
        return {"remote": clean_name, "type": "unknown", "underlying": clean_name, "account_id": ""}

    cp = configparser.ConfigParser()
    try:
        cp.read(conf_path, encoding="utf-8")
    except Exception as e:
        print(f"[!] Error reading rclone config in resolve_remote_info: {e}")
        return {"remote": clean_name, "type": "unknown", "underlying": clean_name, "account_id": ""}

    visited = set()
    cur = clean_name
    remote_type = "unknown"
    account_id = ""

    while cur and cur not in visited:
        visited.add(cur)
        if cur not in cp:
            break
        sec = dict(cp[cur])
        cur_type = sec.get("type", "unknown")
        if remote_type == "unknown":
            remote_type = cur_type
        if cur_type in ("crypt", "alias"):
            target_path = sec.get("remote", "")
            cur = target_path.split(":")[0].strip()
            continue
        elif cur_type == "drive":
            remote_type = "drive"
            account_id = sec.get("client_id", "") or sec.get("team_drive", "") or cur
            break
        else:
            break

    return {
        "remote": clean_name,
        "type": remote_type,
        "underlying": cur or clean_name,
        "account_id": account_id
    }

def sanitize_rclone_flags(flags=None, is_google_drive=False):
    """
    Sanitizes rclone flags for transactions.
    - Uses DEFAULT_RCLONE_FLAGS if none provided.
    - Strips --fast-list for Google Drive remotes to prevent recursive pacer backoff.
    """
    if flags is None:
        flags = list(DEFAULT_RCLONE_FLAGS)
    elif isinstance(flags, str):
        flags = flags.strip().split()
    else:
        flags = list(flags)

    sanitized = []
    for f in flags:
        f_clean = f.strip()
        if not f_clean:
            continue
        if is_google_drive and (f_clean == "--fast-list" or f_clean.startswith("--fast-list=")):
            # Stripped: avoids recursive pacer backoff and 403 userRateLimitExceeded on Google Drive
            continue
        sanitized.append(f_clean)

    return sanitized

def check_cross_drive_sharing(source, dest, rclone_flags=None):
    """
    Pre-flight validation for cross-drive server-side copying.
    Detects if source and destination are separate Google Drive accounts.
    If --drive-server-side-across-configs is used without shared permissions,
    Google Drive API throws: 'googleapi: Error 404: File not found: ..., notFound'.
    """
    src_rem = parse_remote_name(source)
    dst_rem = parse_remote_name(dest)
    src_info = resolve_remote_info(src_rem)
    dst_info = resolve_remote_info(dst_rem)

    flags = rclone_flags or []
    if isinstance(flags, str):
        flags = flags.split()

    has_across_flag = any(
        f == "--drive-server-side-across-configs" or f.startswith("--drive-server-side-across-configs=")
        for f in flags
    )

    is_src_drive = (src_info.get("type") == "drive")
    is_dst_drive = (dst_info.get("type") == "drive")
    is_cross_account = False
    warning = None
    advice = None

    if is_src_drive and is_dst_drive:
        src_acc = src_info.get("account_id") or src_info.get("underlying")
        dst_acc = dst_info.get("account_id") or dst_info.get("underlying")
        if src_acc != dst_acc:
            is_cross_account = True
            advice = (
                f"Ensure destination account '{dst_info.get('underlying')}' has at least Viewer "
                f"permissions on the source folder in Google Drive ('{src_info.get('underlying')}')."
            )
            if has_across_flag:
                warning = (
                    f"Cross-account server-side copy (--drive-server-side-across-configs) between "
                    f"'{src_rem}' ({src_info.get('underlying')}) and '{dst_rem}' ({dst_info.get('underlying')}) "
                    f"requires source folder sharing. Without it, Google Drive returns 404 notFound."
                )

    return {
        "status": "warning" if (is_cross_account and has_across_flag) else "ok",
        "is_cross_account": is_cross_account,
        "is_src_drive": is_src_drive,
        "is_dst_drive": is_dst_drive,
        "source_remote": src_rem,
        "source_underlying": src_info.get("underlying"),
        "dest_remote": dst_rem,
        "dest_underlying": dst_info.get("underlying"),
        "has_across_configs_flag": has_across_flag,
        "warning": warning,
        "advice": advice
    }

def load_transactions():
    """Loads transactions from disk with validation and corruption recovery."""
    with STATE_LOCK:
        if os.path.exists(TX_STORE_PATH):
            try:
                with open(TX_STORE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    print(f"[!] Warning: {TX_STORE_PATH} is not a JSON list (type={type(data).__name__}). Quarantining.")
            except Exception as e:
                print(f"[!] Error loading transactions from {TX_STORE_PATH}: {e}. Quarantining.")

            # Quarantine corrupt or invalid file to prevent unrecoverable loops
            try:
                ts = int(time.time())
                backup_path = f"{TX_STORE_PATH}.corrupt-{ts}"
                os.replace(TX_STORE_PATH, backup_path)
                print(f"[*] Quarantined invalid transaction store to {backup_path}")
            except Exception as q_err:
                print(f"[!] Failed to quarantine {TX_STORE_PATH}: {q_err}")
        return []

def save_transactions(tx_list):
    """Saves transactions to disk atomically."""
    with STATE_LOCK:
        return atomic_write_json(TX_STORE_PATH, tx_list)

def get_transaction_by_id(tx_id):
    """Retrieves a single transaction by ID."""
    with STATE_LOCK:
        for tx in load_transactions():
            if isinstance(tx, dict) and tx.get("tx_id") == tx_id:
                return tx
        return None

def update_transaction(tx_id, updates):
    """Updates fields of an existing transaction."""
    with STATE_LOCK:
        tx_list = load_transactions()
        found = False
        for i, tx in enumerate(tx_list):
            if isinstance(tx, dict) and tx.get("tx_id") == tx_id:
                tx.update(updates)
                tx["updated_at"] = int(time.time())
                tx_list[i] = tx
                found = True
                break
        if found:
            save_transactions(tx_list)
        return found

def create_transaction(source=None, dest="", title=None, mode="copy", priority="normal", rclone_flags=None, notes=""):
    """Creates a new duplication transaction with preflight cross-account and flag validation."""
    if not source:
        primary = get_primary_remote()
        source = f"{primary}library" if primary else ""
    tx_id = f"dup-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(2)}"

    src_info = resolve_remote_info(parse_remote_name(source))
    dst_info = resolve_remote_info(parse_remote_name(dest))
    is_drive = (src_info.get("type") == "drive" or dst_info.get("type") == "drive")

    sanitized_flags = sanitize_rclone_flags(rclone_flags, is_google_drive=is_drive)
    validation = check_cross_drive_sharing(source, dest, sanitized_flags)

    combined_notes = notes
    if validation.get("warning"):
        combined_notes = f"{notes}\n[Notice] {validation['warning']}".strip()

    new_tx = {
        "tx_id": tx_id,
        "title": title or f"{source} -> {dest}",
        "source": source,
        "dest": dest,
        "mode": mode,
        "priority": priority,
        "rclone_flags": sanitized_flags,
        "notes": combined_notes,
        "status": "QUEUED",
        "assigned_worker": None,
        "lease_id": 0,
        "offset_bytes": 0,
        "bytes_transferred": 0,
        "total_bytes": 0,
        "files_checked": 0,
        "files_transferred": 0,
        "total_files": 0,
        "percentage": 0.0,
        "speed_bps": 0,
        "speed_human": "0 B/s",
        "eta_sec": 0,
        "current_file": "Queued",
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "preflight": validation
    }
    with STATE_LOCK:
        tx_list = load_transactions()
        tx_list.insert(0, new_tx)
        save_transactions(tx_list)
    return new_tx

def assign_transaction(tx_id, worker_id):
    """Assigns transaction to worker and increments lease_id."""
    with STATE_LOCK:
        tx = get_transaction_by_id(tx_id)
        if not tx:
            return None
        new_lease = tx.get("lease_id", 0) + 1
        update_transaction(tx_id, {
            "status": "RUNNING",
            "assigned_worker": worker_id,
            "lease_id": new_lease
        })
        return new_lease

def pause_transaction(tx_id):
    """Pauses transaction and snapshots offset bytes."""
    with STATE_LOCK:
        tx = get_transaction_by_id(tx_id)
        if not tx:
            return False
        update_transaction(tx_id, {
            "status": "PAUSED",
            "offset_bytes": tx.get("bytes_transferred", 0),
            "assigned_worker": None
        })
        return True

def requeue_transaction(tx_id):
    """Re-queues a paused, interrupted, or finished transaction."""
    with STATE_LOCK:
        tx = get_transaction_by_id(tx_id)
        if not tx:
            return False
        update_transaction(tx_id, {
            "status": "QUEUED",
            "assigned_worker": None,
            "speed_human": "0 B/s"
        })
        return True

def reset_transaction_progress(tx_id):
    """Resets transferred counters back to 0."""
    with STATE_LOCK:
        tx = get_transaction_by_id(tx_id)
        if not tx:
            return False
        update_transaction(tx_id, {
            "offset_bytes": 0,
            "bytes_transferred": 0,
            "percentage": 0.0,
            "files_transferred": 0,
            "files_checked": 0,
            "speed_human": "0 B/s",
            "current_file": "Reset"
        })
        return True

def cancel_transaction(tx_id):
    """Marks transaction as cancelled."""
    with STATE_LOCK:
        tx = get_transaction_by_id(tx_id)
        if not tx:
            return False
        update_transaction(tx_id, {
            "status": "CANCELLED",
            "assigned_worker": None
        })
        return True

def delete_transaction(tx_id):
    """Permanently deletes a transaction."""
    with STATE_LOCK:
        tx_list = load_transactions()
        filtered = [tx for tx in tx_list if isinstance(tx, dict) and tx.get("tx_id") != tx_id]
        if len(filtered) < len(tx_list):
            save_transactions(filtered)
            return True
        return False

def clear_completed_transactions():
    """Removes all completed and cancelled transactions."""
    with STATE_LOCK:
        tx_list = load_transactions()
        filtered = [tx for tx in tx_list if isinstance(tx, dict) and tx.get("status") not in ("COMPLETED", "CANCELLED")]
        cleared = len(tx_list) - len(filtered)
        if cleared > 0:
            save_transactions(filtered)
        return cleared

def record_worker_telemetry(wid, tx_id, reported_lease, req_data):
    """
    Records worker telemetry with strict lease-fencing.
    Returns (status_code, response_data).
    """
    with STATE_LOCK:
        tx = get_transaction_by_id(tx_id)
        if not tx:
            return 404, {"status": "error", "message": "Transaction Not Found"}

        # Lease fencing
        current_lease = tx.get("lease_id", 0)
        if reported_lease != current_lease:
            return 409, {"status": "error", "message": "LEASE_SUPERSEDED"}

        status = req_data.get("status", "RUNNING")
        if status == "COMPLETED":
            update_transaction(tx_id, {
                "status": "COMPLETED",
                "percentage": 100.0,
                "current_file": "Finished",
                "speed_human": "0 B/s"
            })
            return 200, {"status": "ok", "state": "COMPLETED"}
        elif status in ("FAILED", "ERROR"):
            err_msg = req_data.get("error_message") or req_data.get("message") or "Transaction Failed"
            update_transaction(tx_id, {
                "status": "FAILED",
                "current_file": f"Failed: {err_msg}",
                "speed_human": "0 B/s",
                "assigned_worker": None
            })
            return 200, {"status": "ok", "state": "FAILED"}
        elif status == "INTERRUPTED":
            err_msg = req_data.get("error_message") or "Interrupted by runner"
            update_transaction(tx_id, {
                "status": "PAUSED",
                "current_file": f"Interrupted: {err_msg}",
                "speed_human": "0 B/s",
                "assigned_worker": None
            })
            return 200, {"status": "ok", "state": "PAUSED"}
        else:
            offset = tx.get("offset_bytes", 0)
            r_bytes = req_data.get("bytes", 0)
            r_total = req_data.get("total_bytes", 0)

            total_transferred = offset + r_bytes
            est_total = max(tx.get("total_bytes", 0), offset + r_total)
            pct = round((total_transferred / est_total) * 100, 1) if est_total > 0 else 0.0

            update_transaction(tx_id, {
                "status": "RUNNING",
                "bytes_transferred": total_transferred,
                "total_bytes": est_total,
                "percentage": min(100.0, pct),
                "speed_bps": req_data.get("speed_bps", 0),
                "speed_human": f"{format_size(req_data.get('speed_bps', 0))}/s",
                "eta_sec": req_data.get("eta_sec", 0),
                "current_file": req_data.get("current_file", ""),
                "files_checked": req_data.get("checks", 0),
                "files_transferred": req_data.get("transfers", 0)
            })
            return 200, {"status": "ok", "state": "RUNNING"}
