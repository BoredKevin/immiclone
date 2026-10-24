# Handover Specification: Immiclone Dashboard Refactor (v2 - Hardened)

This document is a complete, self-contained implementation prompt and architectural guide. It contains all domain context, concurrency safeguards, data schemas, module boundaries, and step-by-step instructions needed to refactor the monolithic `dashboard/server.py` into a modular, maintainable, production-grade codebase.

---

## 1. Project Background & Context

### What is Immiclone?
**Immiclone** is an infrastructure management and cloud-to-cloud duplication engine for self-hosted [Immich](https://immich.app/) photo/video backup servers.

### The Problem It Solves:
* **Hybrid Storage**: Immich originals are stored in an encrypted cloud mount (`bkc:` / Google Drive via Rclone), while thumbnails and video previews are pinned to local SSD to eliminate cloud latency while adhering to a strict local disk limit.
* **Ephemeral Cloud Duplication**: Instead of burdening the local server's disk or upload bandwidth to replicate gigabytes/terabytes of photos to backup clouds (e.g. Terabox or a secondary Google Drive), Immiclone runs a centralized **Duplication Transaction Manager**.
* **Stateless Compute Workers**: Ephemeral worker scripts (`worker.sh`) run in Google Cloud Shell or spot VMs. They fetch Rclone configurations into volatile `/dev/shm` RAM-disk, connect to the server over a private Tailscale network, and pull assigned duplication transactions. If a worker disconnects mid-transfer, another worker can resume the transaction with 1 click without losing progress.

### Current Problem:
`dashboard/server.py` is currently a single **monolithic file (~2,500 lines, 115 KB)** containing:
1. Hardcoded server configuration & file paths.
2. In-memory worker lookup tables and lock synchronization.
3. Tailscale API client and OAuth token exchange.
4. Transaction persistence & lease-fencing engine.
5. Local VFS cache scanner & Rclone RC query client.
6. A 5-second background watchdog thread for worker heartbeats.
7. An embedded **1,200+ line HTML/CSS/JavaScript single-page application** string.
8. A monolithic HTTP `do_GET` and `do_POST` router with dozens of nested endpoints.

---

## 2. Hard Constraints & Architectural Invariants

1. **Pure Python Standard Library Only**: The remote Debian host (`babel`) runs the service directly under systemd using system Python 3 (`/usr/bin/python3`). **Do NOT introduce external pip dependencies** (like `Flask`, `FastAPI`, `aiohttp`, `requests`, or `pydantic`). Use standard `http.server`, `socketserver`, `urllib.request`, `urllib.parse`, `json`, `threading`, `time`, and `secrets`.
2. **Maintain Exact API Contracts**: The worker script (`worker.sh`) and dashboard client rely on exact endpoints, JSON payloads, and SSE stream structures.
3. **Persistent File Locations**: By default, state files are stored at:
   * Transactions: `/home/kevin/immich-app/duplication_transactions.json`
   * Workers Registry: `/home/kevin/immich-app/workers_registry.json`
   * Tailscale Config: `/home/kevin/immich-app/tailscale_config.json`
   * Master Rclone: `/root/.config/rclone/rclone.conf`
   *(Make these paths configurable via environment variables with these safe defaults).*
4. **Lease Fencing & Resumption Logic**:
   * Transactions have a monotonically increasing `lease_id`.
   * When workers report telemetry, outdated leases are rejected with `409 LEASE_SUPERSEDED`.
   * Resumed transfers must retain `offset_bytes` so progress continues seamlessly.
5. **500ms SSE Telemetry Stream**: The `/api/stream` endpoint must flush live events without buffering.

---

## 3. 7 Critical Concurrency & Technical Safeguards

To prevent runtime deadlocks, false-positive watchdog timeouts, cross-device filesystem crashes, and security holes during extraction, the following 7 safeguards **must** be implemented:

### A. Split Locks (`STATE_LOCK` vs `SCAN_LOCK`)
* **The Problem**: If a single `GLOBAL_LOCK` is held while `scanner.py` walks `/var/cache/rclone-gda` or `/mnt/gda` (where a Fuse/Rclone mount can hang for 2–4 seconds), all worker heartbeats, SSE 500ms pushes, and telemetry reports block, triggering false-positive 15s watchdog timeouts.
* **The Rule**: In `config.py`, define two distinct locks:
  * `STATE_LOCK = threading.RLock()`: Strictly for in-memory worker/transaction state mutations and atomic JSON persistence.
  * `SCAN_LOCK = threading.Lock()`: Exclusively for `scanner.py` filesystem walks so only one thread runs `os.walk` at a time without blocking state operations.

### B. Cross-Module Import Directed Acyclic Graph (DAG)
To prevent circular import errors (`ImportError` on startup), enforce this strict hierarchy:
```
1. config.py (imports nothing internal)
2. tailscale.py, transactions.py (import only config)
3. workers.py (imports config, tailscale)
4. watchdog.py, scanner.py (orchestration layer: import config, workers, transactions, tailscale)
5. handlers/* (import services/* and config)
6. server.py (imports handlers, services, config)
```

### C. RequestHandler Mixin Pattern
`http.server.BaseHTTPRequestHandler` instantiates a new handler instance per request.
* `handlers/base.py` defines `BaseHandler(http.server.BaseHTTPRequestHandler)` containing shared helpers (`send_json`, `send_text`, `read_json_body`, static file delivery).
* `handlers/api_get.py` defines `GetRoutesMixin` (containing `handle_get(self, path, query)`).
* `handlers/api_post.py` defines `PostRoutesMixin` (containing `handle_post(self, path, req_data)`).
* `server.py` combines them:
  ```python
  class DashboardHandler(GetRoutesMixin, PostRoutesMixin, BaseHandler):
      def do_GET(self):
          self.handle_get()
      def do_POST(self):
          self.handle_post()
  ```

### D. Static File Path Traversal Guard
Serving static files via `os.path.join` must guard against path traversal attacks (e.g., `/static/../../../../root/.config/rclone/rclone.conf`):
```python
real_static = os.path.realpath(os.path.join(DASHBOARD_DIR, "static"))
target_path = os.path.realpath(os.path.join(real_static, rel_path))
if not target_path.startswith(real_static + os.sep) or not os.path.isfile(target_path):
    self.send_error(403, "Forbidden")
    return
```

### E. Atomic File Write Helper & Cross-Device Safety
Writing JSON state files across filesystems can raise `OSError: [Errno 18] Invalid cross-device link` if temp files are created in `/tmp` (tmpfs) while targets live in `/home/kevin`.
* Implement a shared helper in `config.py`:
  ```python
  def atomic_write_json(filepath, data):
      target_dir = os.path.dirname(os.path.abspath(filepath))
      os.makedirs(target_dir, exist_ok=True)
      tmp_path = f"{filepath}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
      with open(tmp_path, "w", encoding="utf-8") as f:
          json.dump(data, f, indent=2)
      os.replace(tmp_path, filepath)
  ```

### F. SSE Socket Cleanup & Threading
* In `handlers/api_get.py`, catch `(BrokenPipeError, ConnectionResetError, TimeoutError)` inside the `/api/stream` infinite generator loop and `break` cleanly so closed browser tabs do not leak zombie threads.
* On `ThreadedHTTPServer`, explicitly set:
  ```python
  class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
      allow_reuse_address = True
      daemon_threads = True
  ```
  This ensures `systemctl stop` or `Ctrl+C` immediately shuts down without hanging on open SSE connections.

### G. Clean Static Frontend (No Template Variable Leakage)
The extracted `templates/index.html` does not require server-side f-string templating. All live data (storage meters, transactions, workers, remotes) is pulled client-side via `/api/stream` and REST endpoints. `index.html` must cleanly link:
```html
<link rel="stylesheet" href="/static/css/style.css">
<script src="/static/js/app.js"></script>
```

---

## 4. Target Architecture & Directory Layout

```text
dashboard/
├── server.py                  # Bootstrap entrypoint (< 80 lines)
├── config.py                  # Paths, constants, STATE_LOCK, SCAN_LOCK, atomic_write_json
├── templates/
│   └── index.html             # Clean HTML markup (extracted from monolith string)
├── static/
│   ├── css/
│   │   └── style.css          # Extracted CSS styles
│   └── js/
│       └── app.js             # Extracted frontend SPA logic (SSE, DOM, modals)
├── services/
│   ├── __init__.py
│   ├── scanner.py             # Disk usage, VFS cache scanner, Rclone RC queries (SCAN_LOCK)
│   ├── tailscale.py           # Tailscale store, secret masking, API & OAuth token exchange
│   ├── transactions.py        # Duplication transactions store (CRUD, leases, offsets) (STATE_LOCK)
│   ├── workers.py             # Workers store (CRUD, tokens, one-liner generator) (STATE_LOCK)
│   └── watchdog.py            # Background heartbeat monitor thread (15s timeout)
└── handlers/
    ├── __init__.py
    ├── base.py                # BaseHandler with JSON helpers & path-traversal guarded static server
    ├── api_get.py             # GetRoutesMixin (/api/stream, /api/media, /api/worker/*, etc.)
    └── api_post.py            # PostRoutesMixin (/api/tx/*, /api/worker/*, /api/tailscale/*)
```

---

## 5. Module Detailed Responsibilities

### Module 1: `dashboard/config.py`
* Paths with environment overrides: `PORT`, `MOUNT_BASE`, `CACHE_BASE`, `RCLONE_CONF_PATH`, `TX_STORE_PATH`, `WORKERS_STORE_PATH`, `TAILSCALE_CONF_PATH`, `DASHBOARD_DIR`.
* Locks: `STATE_LOCK = threading.RLock()`, `SCAN_LOCK = threading.Lock()`.
* Utilities: `format_size(bytes_size)`, `atomic_write_json(filepath, data)`.

### Module 2: `dashboard/services/tailscale.py`
* Reads/writes `TAILSCALE_CONF_PATH` via `atomic_write_json`.
* Functions: `load_tailscale_config()`, `save_tailscale_config(cfg)`, `mask_secret(s)`, `get_effective_tailscale_key()`, `test_tailscale_connection()`.
* Handles OAuth token exchange (`https://api.tailscale.com/api/v2/oauth/token`) and ephemeral key generation (`/api/v2/tailnet/{tailnet}/keys`).

### Module 3: `dashboard/services/workers.py`
* Synchronizes `WORKERS_STORE_PATH` and in-memory `_active_workers` / `_worker_tokens` protected by `STATE_LOCK`.
* Functions: `init_workers_from_disk()`, `load_workers()`, `save_workers_list()`, `sync_workers_to_disk()`, `get_worker(wid)`, `get_all_workers()`, `create_worker_session(name, notes, include_tailscale)`, `register_worker(wid, hostname)`, `update_worker(wid, updates)`, `disconnect_worker(wid)`, `reset_worker(wid)`, `delete_worker(wid)`, `prune_offline_workers()`.

### Module 4: `dashboard/services/transactions.py`
* Manages `TX_STORE_PATH` protected by `STATE_LOCK`.
* Functions: `load_transactions()`, `save_transactions(tx_list)`, `get_transaction_by_id(tx_id)`, `create_transaction(...)`, `update_transaction(tx_id, updates)`, `assign_transaction(tx_id, worker_id)` *(increments lease_id)*, `pause_transaction(tx_id)` *(preserves offset_bytes)*, `requeue_transaction(tx_id)`, `reset_transaction_progress(tx_id)`, `cancel_transaction(tx_id)`, `delete_transaction(tx_id)`, `clear_completed_transactions()`, `record_worker_telemetry(wid, tx_id, lease_id, report_data)` *(enforces lease fencing)*.

### Module 5: `dashboard/services/scanner.py`
* Parses `RCLONE_CONF_PATH` for available remotes: `get_available_remotes()`.
* Queries Rclone RC on port 5572: `query_rclone(endpoint, payload)`.
* Filesystem scan under `SCAN_LOCK`: `scan_files_if_needed()`.
* Paginated catalog: `get_paginated_media(page, limit, filter_type, search_query)`.
* Unified telemetry builder: `get_live_sse_payload()`.

### Module 6: `dashboard/services/watchdog.py`
* Background thread `watchdog_loop()` running every 5 seconds.
* Marks workers missing for >15s as `OFFLINE`.
* Safely marks active transactions as `INTERRUPTED` and stores `offset_bytes`.

### Module 7: `dashboard/handlers/`
* `handlers/base.py`:
  * `BaseHandler(http.server.BaseHTTPRequestHandler)`:
    * `send_json(data, status=200)`
    * `send_text(content, content_type, status=200)`
    * `read_json_body()`
    * `serve_static(rel_path)` (enforces path traversal guard)
* `handlers/api_get.py`:
  * `GetRoutesMixin`:
    * Dispatches `/api/stream` (SSE generator with `BrokenPipeError` catch), `/api/media`, `/api/tailscale/config`, `/api/worker/remotes`, `/api/tx/list`, `/api/workers`, `/api/worker/poll`, `/api/worker/config`, `/static/*`, and `/` (serves `templates/index.html`).
* `handlers/api_post.py`:
  * `PostRoutesMixin`:
    * Dispatches `/api/tailscale/*`, `/api/worker/*`, and `/api/tx/*`.

### Module 8: `dashboard/server.py`
* Entrypoint:
  ```python
  #!/usr/bin/env python3
  import threading
  import socketserver
  from dashboard.config import PORT
  from dashboard.handlers.base import BaseHandler
  from dashboard.handlers.api_get import GetRoutesMixin
  from dashboard.handlers.api_post import PostRoutesMixin
  from dashboard.services.workers import init_workers_from_disk
  from dashboard.services.watchdog import watchdog_loop

  class DashboardHandler(GetRoutesMixin, PostRoutesMixin, BaseHandler):
      def do_HEAD(self):
          self.send_response(200)
          self.send_header("Content-Type", "text/html; charset=utf-8")
          self.end_headers()

      def do_GET(self):
          self.handle_get()

      def do_POST(self):
          self.handle_post()

  class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
      allow_reuse_address = True
      daemon_threads = True

  if __name__ == "__main__":
      init_workers_from_disk()
      wd = threading.Thread(target=watchdog_loop, daemon=True)
      wd.start()
      with ThreadedHTTPServer(("0.0.0.0", PORT), DashboardHandler) as httpd:
          print(f"[*] Immiclone Dashboard listening on 0.0.0.0:{PORT}")
          httpd.serve_forever()
  ```

---

## 6. Verification Checklist

1. **Syntax Validation**:
   ```bash
   python3 -m py_compile dashboard/config.py
   python3 -m py_compile dashboard/services/*.py
   python3 -m py_compile dashboard/handlers/*.py
   python3 -m py_compile dashboard/server.py
   ```
2. **Server Startup**:
   Run `python3 dashboard/server.py` and confirm clean binding to port 8080.
3. **Static & HTML Delivery**:
   * `curl -I http://localhost:8080/` -> `HTTP/1.1 200 OK`, `text/html`
   * `curl -I http://localhost:8080/static/css/style.css` -> `HTTP/1.1 200 OK`, `text/css`
   * `curl -I http://localhost:8080/static/js/app.js` -> `HTTP/1.1 200 OK`, `application/javascript`
   * Path traversal attack test: `curl -I "http://localhost:8080/static/../../../../etc/passwd"` -> `HTTP/1.1 403 Forbidden`
4. **SSE Stream Connection**:
   * `curl -N http://localhost:8080/api/stream` -> delivers 500ms JSON chunks without blocking.
   * Closing the `curl` connection terminates the thread cleanly without traceback errors.
5. **Lease-Fencing Verification**:
   * Post telemetry with an outdated `lease_id` -> verify response is `409 Conflict` with `LEASE_SUPERSEDED`.
