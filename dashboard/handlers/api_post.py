import time
import urllib.parse
from dashboard.config import (
    APP_VERSION,
    STATE_LOCK,
    get_app_config,
    save_app_config,
    get_primary_remote
)
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
from dashboard.services.updater import check_for_updates

class PostRoutesMixin:
    """POST Request routing mixin for DashboardHandler supporting canonical /api/v1/ routes."""

    def handle_post(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        req_data = self.read_json_body()

        canonical_path = self.normalize_api_path(path)

        # -------------------------------------------------------------
        # APPLICATION UPDATES CHECKER TRIGGER
        # -------------------------------------------------------------
        if canonical_path == "/api/v1/updates/check":
            info = check_for_updates(force=True)
            self.send_json(info)
            return

        # -------------------------------------------------------------
        # APPLICATION SETTINGS CRUD
        # -------------------------------------------------------------
        elif canonical_path == "/api/v1/settings" or canonical_path == "/api/v1/settings/save":
            current_cfg = get_app_config()
            if "general" in req_data and isinstance(req_data["general"], dict):
                current_cfg["general"].update(req_data["general"])
            if "storage" in req_data and isinstance(req_data["storage"], dict):
                current_cfg["storage"].update(req_data["storage"])
            save_app_config(current_cfg)
            self.send_json({"status": "ok", "settings": current_cfg})
            return

        # -------------------------------------------------------------
        # TAILSCALE CONFIGURATION CRUD
        # -------------------------------------------------------------
        elif canonical_path == "/api/v1/tailscale/save":
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

        elif canonical_path == "/api/v1/tailscale/delete":
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

        elif canonical_path == "/api/v1/tailscale/test":
            resp = test_tailscale_connection()
            self.send_json(resp)
            return

        # -------------------------------------------------------------
        # WORKER CRUD
        # -------------------------------------------------------------
        elif canonical_path == "/api/v1/worker/create-session":
            name = req_data.get("name")
            notes = req_data.get("notes")
            include_ts = req_data.get("include_tailscale", True)
            force_fresh = bool(req_data.get("force_fresh", False))
            host_header = self.headers.get("Host")
            session = create_worker_session(name=name, notes=notes, include_tailscale=include_ts, request_host=host_header, force_fresh=force_fresh)
            self.send_json(session)
            return

        elif canonical_path == "/api/v1/worker/create":
            name = req_data.get("name")
            notes = req_data.get("notes", "")
            wid = create_custom_worker(name=name, notes=notes)
            self.send_json({"status": "ok", "worker_id": wid})
            return

        elif canonical_path == "/api/v1/worker/update":
            wid = req_data.get("worker_id", "")
            updates = {}
            if "name" in req_data: updates["name"] = req_data["name"]
            if "notes" in req_data: updates["notes"] = req_data["notes"]
            if update_worker(wid, updates):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Worker Not Found")
            return

        elif canonical_path == "/api/v1/worker/disconnect":
            wid = req_data.get("worker_id", "")
            if disconnect_worker(wid):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Worker Not Found")
            return

        elif canonical_path == "/api/v1/worker/reset":
            wid = req_data.get("worker_id", "")
            if reset_worker(wid):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Worker Not Found")
            return

        elif canonical_path == "/api/v1/worker/delete":
            wid = req_data.get("worker_id", "")
            if delete_worker(wid):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Worker Not Found")
            return

        elif canonical_path == "/api/v1/worker/prune-offline":
            removed = prune_offline_workers()
            self.send_json({"status": "ok", "removed": removed})
            return

        elif canonical_path == "/api/v1/worker/register":
            wid = req_data.get("worker_id", "")
            hostname = req_data.get("hostname", "unknown")
            worker_version = req_data.get("version") or self.headers.get("X-Worker-Version", "unknown")
            client_ip = self.client_address[0] if getattr(self, "client_address", None) else "unknown"
            version_match = (worker_version == APP_VERSION)
            print(f"[+] Worker connected: {wid} ({hostname}, v{worker_version}, match={version_match}) from {client_ip}")
            register_worker(wid, hostname, version=worker_version)
            self.send_json({
                "status": "ok",
                "message": "Registered",
                "server_version": APP_VERSION,
                "worker_version": worker_version,
                "version_match": version_match
            })
            return

        elif canonical_path == "/api/v1/worker/report":
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
        elif canonical_path == "/api/v1/tx/create":
            primary = get_primary_remote()
            default_src = f"{primary}library" if primary else ""
            src = req_data.get("source") or default_src
            dst = req_data.get("dest", "")
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

        elif canonical_path == "/api/v1/tx/update":
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

        elif canonical_path == "/api/v1/tx/assign":
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

        elif canonical_path == "/api/v1/tx/pause":
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

        elif canonical_path == "/api/v1/tx/requeue":
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

        elif canonical_path == "/api/v1/tx/reset-progress":
            tx_id = req_data.get("tx_id", "")
            if reset_transaction_progress(tx_id):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Transaction Not Found")
            return

        elif canonical_path == "/api/v1/tx/cancel":
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

        elif canonical_path == "/api/v1/tx/delete":
            tx_id = req_data.get("tx_id", "")
            if delete_transaction(tx_id):
                self.send_json({"status": "ok"})
            else:
                self.send_error_msg(404, "Transaction Not Found")
            return

        elif canonical_path == "/api/v1/tx/clear-completed":
            cleared = clear_completed_transactions()
            self.send_json({"status": "ok", "cleared": cleared})
            return

        else:
            self.send_error_msg(404, "Not Found")
            return
