import os
import json
import time
import secrets
from datetime import datetime
from dashboard.config import TX_STORE_PATH, STATE_LOCK, atomic_write_json, format_size

def load_transactions():
    """Loads transactions from disk."""
    with STATE_LOCK:
        if os.path.exists(TX_STORE_PATH):
            try:
                with open(TX_STORE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Error loading transactions: {e}")
        return []

def save_transactions(tx_list):
    """Saves transactions to disk atomically."""
    with STATE_LOCK:
        return atomic_write_json(TX_STORE_PATH, tx_list)

def get_transaction_by_id(tx_id):
    """Retrieves a single transaction by ID."""
    with STATE_LOCK:
        for tx in load_transactions():
            if tx.get("tx_id") == tx_id:
                return tx
        return None

def update_transaction(tx_id, updates):
    """Updates fields of an existing transaction."""
    with STATE_LOCK:
        tx_list = load_transactions()
        found = False
        for i, tx in enumerate(tx_list):
            if tx.get("tx_id") == tx_id:
                tx.update(updates)
                tx["updated_at"] = int(time.time())
                tx_list[i] = tx
                found = True
                break
        if found:
            save_transactions(tx_list)
        return found

def create_transaction(source="bkc:library", dest="tbc:library", title=None, mode="copy", priority="normal", rclone_flags=None, notes=""):
    """Creates a new duplication transaction."""
    tx_id = f"dup-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(2)}"
    new_tx = {
        "tx_id": tx_id,
        "title": title or f"{source} -> {dest}",
        "source": source,
        "dest": dest,
        "mode": mode,
        "priority": priority,
        "rclone_flags": rclone_flags or ["--size-only", "--transfers=4", "--checkers=8", "--tpslimit=4"],
        "notes": notes,
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
        "updated_at": int(time.time())
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
        filtered = [tx for tx in tx_list if tx.get("tx_id") != tx_id]
        if len(filtered) < len(tx_list):
            save_transactions(filtered)
            return True
        return False

def clear_completed_transactions():
    """Removes all completed and cancelled transactions."""
    with STATE_LOCK:
        tx_list = load_transactions()
        filtered = [tx for tx in tx_list if tx.get("status") not in ("COMPLETED", "CANCELLED")]
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
