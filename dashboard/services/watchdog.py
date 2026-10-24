import time
from dashboard.config import STATE_LOCK
from dashboard.services.workers import get_active_workers_dict, sync_workers_to_disk
from dashboard.services.transactions import get_transaction_by_id, update_transaction

def watchdog_loop():
    """Background watchdog thread monitoring worker heartbeats every 5 seconds."""
    while True:
        time.sleep(5)
        now = time.time()
        with STATE_LOCK:
            changed = False
            active_workers = get_active_workers_dict()
            for wid, worker in list(active_workers.items()):
                if worker.get("status") != "OFFLINE" and (now - worker.get("last_seen", 0) > 15.0):
                    print(f"[!] Worker {wid} timed out (>15s). Marking OFFLINE.")
                    worker["status"] = "OFFLINE"
                    changed = True
                    
                    tx_id = worker.get("current_tx")
                    if tx_id:
                        tx = get_transaction_by_id(tx_id)
                        if tx and tx.get("status") == "RUNNING":
                            print(f"[!] Marking transaction {tx_id} as INTERRUPTED (Resume ready).")
                            update_transaction(tx_id, {
                                "status": "INTERRUPTED",
                                "offset_bytes": tx.get("bytes_transferred", 0),
                                "assigned_worker": None
                            })
                        worker["current_tx"] = None
            if changed:
                sync_workers_to_disk()
