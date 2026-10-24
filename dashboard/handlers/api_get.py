import os
import json
import time
import urllib.parse
from dashboard.config import (
    STATE_LOCK,
    WORKER_SCRIPT_PATH,
    get_app_config,
    get_rclone_conf_path,
    get_version_metadata
)
from dashboard.services.scanner import (
    get_live_sse_payload,
    get_paginated_media,
    get_available_remotes
)
from dashboard.services.tailscale import load_tailscale_config, mask_secret
from dashboard.services.transactions import load_transactions, get_transaction_by_id
from dashboard.services.workers import (
    load_workers,
    get_worker,
    verify_worker_token
)
from dashboard.services.updater import get_update_status, check_for_updates

class GetRoutesMixin:
    """GET Request routing mixin for DashboardHandler supporting canonical /api/v1/ routes."""

    def handle_get(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. SERVE WORKER SCRIPT DIRECTLY (Zero-CDN, Self-Contained Runner)
        if path == "/worker.sh":
            if os.path.exists(WORKER_SCRIPT_PATH):
                try:
                    with open(WORKER_SCRIPT_PATH, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/x-shellscript; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    print(f"[!] Error reading worker.sh: {e}")
                    self.send_error_msg(500, "Error reading worker script")
                    return
            else:
                self.send_error_msg(404, "worker.sh not found")
                return

        # 2. STATIC ASSET SERVING
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            self.serve_static(rel_path)
            return

        # Canonicalize API version: /api/* -> /api/v1/*
        canonical_path = self.normalize_api_path(path)

        # 3. APPLICATION VERSION & SEMVER METADATA
        if canonical_path == "/api/v1/version":
            self.send_json(get_version_metadata())
            return

        # 4. APPLICATION UPDATE STATUS & CHECKER
        elif canonical_path == "/api/v1/updates":
            force = query.get("force", ["false"])[0].lower() in ("true", "1")
            self.send_json(check_for_updates(force=force) if force else get_update_status())
            return

        # 5. SSE STREAM (Live 500ms Telemetry Broadcast)
        elif canonical_path == "/api/v1/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                while True:
                    payload = get_live_sse_payload()
                    msg = f"data: {json.dumps(payload)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                # Socket cleanly disconnected by client (browser tab closed)
                pass
            return

        # 6. APPLICATION SETTINGS API
        elif canonical_path == "/api/v1/settings":
            cfg = get_app_config()
            self.send_json({
                "general": cfg.get("general", {}),
                "storage": cfg.get("storage", {}),
                "detected_remotes": get_available_remotes()
            })
            return

        # 7. PAGINATED MEDIA CATALOG API
        elif canonical_path == "/api/v1/media":
            page = int(query.get("page", ["1"])[0])
            limit = int(query.get("limit", ["50"])[0])
            filter_type = query.get("filter", ["all"])[0]
            search_query = query.get("q", [""])[0]

            data = get_paginated_media(page=page, limit=limit, filter_type=filter_type, search_query=search_query)
            self.send_json(data)
            return

        # 9. TAILSCALE CONFIGURATION
        elif canonical_path == "/api/v1/tailscale/config":
            cfg = load_tailscale_config()
            resp = {
                "mode": cfg.get("mode", "auth_key"),
                "masked_key": mask_secret(cfg.get("auth_key", "")),
                "masked_api": mask_secret(cfg.get("api_key", "")),
                "tailnet": cfg.get("tailnet", ""),
                "auto_inject": cfg.get("auto_inject", True),
                "ephemeral": cfg.get("ephemeral", True),
                "last_updated": cfg.get("last_updated", 0)
            }
            self.send_json(resp)
            return

        # 10. AVAILABLE REMOTES LIST
        elif canonical_path == "/api/v1/worker/remotes":
            remotes = get_available_remotes()
            self.send_json({"remotes": remotes})
            return

        # 11. TRANSACTIONS LIST
        elif canonical_path == "/api/v1/tx/list":
            tx_list = load_transactions()
            self.send_json(tx_list)
            return

        # 12. WORKERS LIST
        elif canonical_path == "/api/v1/workers":
            workers = load_workers()
            self.send_json(workers)
            return

        # 13. WORKER POLL ENDPOINT (Polled by worker.sh every 1s)
        elif canonical_path == "/api/v1/worker/poll":
            wid = query.get("id", [""])[0]
            with STATE_LOCK:
                worker = get_worker(wid)
                if worker:
                    worker["last_seen"] = time.time()
                    if worker.get("status") == "OFFLINE":
                        worker["status"] = "STANDBY"

                    # Check for pending admin termination signals
                    pending = worker.get("pending_action")
                    if pending == "STOP":
                        worker["pending_action"] = None
                        resp = {"action": "STOP", "terminate": True, "reason": "USER_DISCONNECT"}
                        self.send_json(resp)
                        return

                    tx_id = worker.get("current_tx")
                    if tx_id:
                        tx = get_transaction_by_id(tx_id)
                        if tx and tx.get("status") == "RUNNING":
                            resp = {
                                "action": "RUN_TRANSACTION",
                                "tx": {
                                    "tx_id": tx["tx_id"],
                                    "lease_id": tx.get("lease_id", 1),
                                    "source": tx["source"],
                                    "dest": tx["dest"],
                                    "mode": tx.get("mode", "copy"),
                                    "rclone_flags": tx.get("rclone_flags", ["--size-only", "--transfers=4", "--checkers=8", "--tpslimit=4"])
                                }
                            }
                        elif tx and tx.get("status") == "PAUSED":
                            resp = {"action": "PAUSE"}
                        elif tx and tx.get("status") == "CANCELLED":
                            resp = {"action": "STOP"}
                        else:
                            resp = {"action": "STANDBY"}
                    else:
                        resp = {"action": "STANDBY"}
                else:
                    resp = {"action": "STANDBY"}

            self.send_json(resp)
            return

        # 14. SERVE RCLONE CONFIG TO AUTHORIZED RUNNER (IN VOLATILE RAM)
        elif canonical_path == "/api/v1/worker/config":
            wid = query.get("id", [""])[0]
            token = query.get("token", [""])[0]
            conf_path = get_rclone_conf_path()
            if verify_worker_token(wid, token) and os.path.exists(conf_path):
                try:
                    with open(conf_path, "rb") as f:
                        conf_bytes = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(conf_bytes)))
                    self.end_headers()
                    self.wfile.write(conf_bytes)
                    return
                except Exception as e:
                    print(f"[!] Error serving config: {e}")

            self.send_error_msg(403, "Forbidden")
            return

        # 15. ROOT DASHBOARD HTML
        else:
            self.serve_index()
            return
