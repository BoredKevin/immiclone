import time
import urllib.parse
from dashboard.config import STATE_LOCK
from dashboard.services.tailscale import (
    load_tailscale_config,
    save_tailscale_config,
    test_tailscale_connection
)
from dashboard.services.workers import (
    create_worker_session,
    create_custom_worker,
    update_worker,
    disconnect_worker,
    reset_worker,
    delete_worker,
    prune_offline_workers,
    register_worker,
    get_worker,
    sync_workers_to_disk
)
from dashboard.services.transactions import (
    create_transaction,
    update_transaction,
    assign_transaction,
    pause_transaction,
    requeue_transaction,
    reset_transaction_progress,
    cancel_transaction,
    delete_transaction,
    clear_completed_transactions,
    record_worker_telemetry,
    get_transaction_by_id
)

class PostRoutesMixin:
    """POST Request routing mixin for DashboardHandler."""

    def handle_post(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        req_data = self.read_json_body()

        # -------------------------------------------------------------
        # TAILSCALE CONFIGURATION CRUD
        # -------------------------------------------------------------
        if path == "/api/tailscale/save":
            cfg = load_tailscale_config()
            cfg["mode"] = req_data.get("mode", cfg.get("mode", "auth_key"))
            if req_data.get("auth_key"):
                cfg["auth_key"] = req_data.get("auth_key")
            if req_data.get("api_key"):
                cfg["api_key"] = req_data.get("api_key")
            if req_data.get("oauth_client_id"):
                cfg["oauth_client_id"] = req_data.get("oauth_client_id")
            if req_data.get("oauth_client_secret"):
                cfg["oauth_client_secret"] = req_data.get("oauth_client_secret")
            if "tailnet" in req_data:
                cfg["tailnet"] = req_data.get("tailnet", "")
            if "auto_inject" in req_data:
                cfg["auto_inject"] = bool(req_data.get("auto_inject"))
            if "ephemeral" in req_data:
                cfg["ephemeral"] = bool(req_data.get("ephemeral"))
            save_tailscale_config(cfg)
            self.send_json({"status": "ok"})
            return

        elif path == "/api/tailscale/delete":
            empty_cfg = {
                "mode": "auth_key",
                "auth_key": "",
                "api_key": "",
                "oauth_client_id": "",
                "oauth_client_secret": "",
                "tailnet": "",
                "auto_inject": True,
                "ephemeral": True,
                "tags": ["tag:worker"],
                "last_updated": int(time.time())
            }
            save_tailscale_config(empty_cfg)
            self.send_json({"status": "ok"})
            return

        elif path == "/api/tailscale/test":
            resp = test_tailscale_connection()
            self.send_json(resp)
            return

        # -------------------------------------------------------------
        # WORKER CRUD
        # -------------------------------------------------------------
        elif path == "/api/worker/create-session":
            name = req_data.get("name")
            notes = req_data.get("notes")
            include_ts = req_data.get("include_tailscale", True)
            session = create_worker_session(name=name, notes=notes, include_tailscale=include_ts)
            self.send_json(session)
            return

        elif path == "/api/worker/create":
            name = req_data.get("name")
            notes = req_data.get("notes", "")
            wid = create_custom_worker(name=name, notes=notes)
            self.send_json({"status": "ok", "worker_id": wid})
            return

        elif path == "/api/worker/update":
            wid = req_data.get("worker_id", "")
            updates = {}
            if "name" in req_data: updates["name"] = req_data["name"]
            if "notes" in req_data: updates["notes"] = req_data["notes"]
            if update_worker(wid, updates):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Worker Not Found")
            return

        elif path == "/api/worker/disconnect":
            wid = req_data.get("worker_id", "")
            if disconnect_worker(wid):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Worker Not Found")
            return

        elif path == "/api/worker/reset":
            wid = req_data.get("worker_id", "")
            if reset_worker(wid):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Worker Not Found")
            return

        elif path == "/api/worker/delete":
            wid = req_data.get("worker_id", "")
            if delete_worker(wid):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Worker Not Found")
            return

        elif path == "/api/worker/prune-offline":
            removed = prune_offline_workers()
            self.send_json({"status": "ok", "removed": removed})
            return

        elif path == "/api/worker/register":
            wid = req_data.get("worker_id", "")
            hostname = req_data.get("hostname", "unknown")
            register_worker(wid, hostname)
            self.send_json({"status": "ok", "message": "Registered"})
            return

        elif path == "/api/worker/report":
            wid = req_data.get("worker_id", "")
            tx_id = req_data.get("tx_id", "")
            reported_lease = req_data.get("lease_id", 0)

            # Update worker heartbeat
            with STATE_LOCK:
                worker = get_worker(wid)
                if worker:
                    worker["last_seen"] = time.time()

            code, resp = record_worker_telemetry(wid, tx_id, reported_lease, req_data)
            if code == 200:
                with STATE_LOCK:
                    worker = get_worker(wid)
                    if worker:
                        if resp.get("state") == "COMPLETED":
                            worker["status"] = "STANDBY"
                            worker["current_tx"] = None
                        else:
                            worker["status"] = "RUNNING"
                            worker["current_tx"] = tx_id
                        sync_workers_to_disk()
                self.send_json(resp)
            else:
                self.send_json(resp, status=code)
            return

        # -------------------------------------------------------------
        # DUPLICATION TRANSACTIONS CRUD
        # -------------------------------------------------------------
        elif path == "/api/tx/create":
            src = req_data.get("source", "bkc:library")
            dst = req_data.get("dest", "tbc:library")
            title = req_data.get("title")
            mode = req_data.get("mode", "copy")
            priority = req_data.get("priority", "normal")
            flags = req_data.get("rclone_flags")
            notes = req_data.get("notes", "")

            tx = create_transaction(
                source=src,
                dest=dst,
                title=title,
                mode=mode,
                priority=priority,
                rclone_flags=flags,
                notes=notes
            )
            self.send_json({"status": "ok", "tx": tx})
            return

        elif path == "/api/tx/update":
            tx_id = req_data.get("tx_id", "")
            updates = {}
            for field in ("title", "source", "dest", "mode", "priority", "rclone_flags", "notes"):
                if field in req_data:
                    updates[field] = req_data[field]
            if update_transaction(tx_id, updates):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Transaction Not Found")
            return

        elif path == "/api/tx/assign":
            tx_id = req_data.get("tx_id", "")
            wid = req_data.get("worker_id", "")
            with STATE_LOCK:
                new_lease = assign_transaction(tx_id, wid)
                if new_lease is not None:
                    worker = get_worker(wid)
                    if worker:
                        worker["current_tx"] = tx_id
                        worker["status"] = "RUNNING"
                        sync_workers_to_disk()
                    self.send_json({"status": "ok", "lease_id": new_lease})
                    return
            self.send_error_msg(400, "Invalid Transaction or Worker")
            return

        elif path == "/api/tx/pause":
            tx_id = req_data.get("tx_id", "")
            with STATE_LOCK:
                tx = get_transaction_by_id(tx_id)
                wid = tx.get("assigned_worker") if tx else None
                if pause_transaction(tx_id):
                    if wid:
                        worker = get_worker(wid)
                        if worker:
                            worker["current_tx"] = None
                            worker["status"] = "STANDBY"
                            sync_workers_to_disk()
                    self.send_json({"status": "ok"})
                    return
            self.send_error_msg(404, "Transaction Not Found")
            return

        elif path == "/api/tx/requeue":
            tx_id = req_data.get("tx_id", "")
            with STATE_LOCK:
                tx = get_transaction_by_id(tx_id)
                wid = tx.get("assigned_worker") if tx else None
                if requeue_transaction(tx_id):
                    if wid:
                        worker = get_worker(wid)
                        if worker:
                            worker["current_tx"] = None
                            worker["status"] = "STANDBY"
                            sync_workers_to_disk()
                    self.send_json({"status": "ok"})
                    return
            self.send_error_msg(404, "Transaction Not Found")
            return

        elif path == "/api/tx/reset-progress":
            tx_id = req_data.get("tx_id", "")
            if reset_transaction_progress(tx_id):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Transaction Not Found")
            return

        elif path == "/api/tx/cancel":
            tx_id = req_data.get("tx_id", "")
            with STATE_LOCK:
                tx = get_transaction_by_id(tx_id)
                wid = tx.get("assigned_worker") if tx else None
                if cancel_transaction(tx_id):
                    if wid:
                        worker = get_worker(wid)
                        if worker:
                            worker["current_tx"] = None
                            worker["status"] = "STANDBY"
                            sync_workers_to_disk()
                    self.send_json({"status": "ok"})
                    return
            self.send_error_msg(404, "Transaction Not Found")
            return

        elif path == "/api/tx/delete":
            tx_id = req_data.get("tx_id", "")
            if delete_transaction(tx_id):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Transaction Not Found")
            return

        elif path == "/api/tx/clear-completed":
            cleared = clear_completed_transactions()
            self.send_json({"status": "ok", "cleared": cleared})
            return

        else:
            self.send_error_msg(404, "Not Found")
            return
