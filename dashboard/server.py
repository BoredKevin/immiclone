#!/usr/bin/env python3
import os
import sys
import signal
import threading
import socketserver

# Ensure parent directory is on sys.path so 'from dashboard.*' imports always resolve (handles symlinks via realpath)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

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

def main():
    init_workers_from_disk()

    # Start background watchdog for worker heartbeat timeouts (15s rule)
    wd = threading.Thread(target=watchdog_loop, daemon=True)
    wd.start()

    try:
        httpd = ThreadedHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    except OSError as e:
        print(f"[CRITICAL] Failed to bind dashboard to 0.0.0.0:{PORT}: {e}", file=sys.stderr)
        err_msg = str(e).lower()
        if getattr(e, 'errno', None) == 98 or "already in use" in err_msg or getattr(e, 'winerror', None) in (10048, 10013):
            print(f"[!] Port {PORT} is already in use by another process. Please free port {PORT} or set PORT environment variable.", file=sys.stderr)
            sys.exit(48)
        sys.exit(1)

    shutdown_event = threading.Event()

    def handle_shutdown(signum, frame):
        if not shutdown_event.is_set():
            shutdown_event.set()
            sig_name = "SIGTERM" if signum == signal.SIGTERM else ("SIGINT" if signum == signal.SIGINT else f"signal {signum}")
            print(f"\n[!] Received {sig_name}, shutting down server gracefully...", flush=True)
            threading.Thread(target=httpd.shutdown, daemon=True).start()

    try:
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    except (ValueError, AttributeError):
        pass

    with httpd:
        print(f"[*] Immiclone Dashboard listening on 0.0.0.0:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[!] Shutting down server...")
        finally:
            print("[*] Dashboard server stopped.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg in ("--mount", "mount"):
            from dashboard.services.mount import run_rclone_mount
            run_rclone_mount()
            sys.exit(0)
        elif arg in ("--mount-check", "mount-check"):
            from dashboard.services.mount import check_rclone_mount
            check_rclone_mount()
            sys.exit(0)
        elif arg in ("--unmount", "unmount"):
            from dashboard.services.mount import run_rclone_unmount
            run_rclone_unmount()
            sys.exit(0)
        elif arg in ("--version", "-v"):
            from dashboard.config import APP_VERSION, API_VERSION
            print(f"Immiclone v{APP_VERSION} (API {API_VERSION})")
            sys.exit(0)
        elif arg in ("--help", "-h"):
            print("Usage: immiclone [OPTIONS]")
            print("  (default)    Start Immiclone Web Dashboard and Duplication Control Center")
            print("  --mount      Start Rclone VFS mount using config from Immiclone dashboard")
            print("  --unmount    Unmount configured Immiclone storage mount base")
            print("  --version    Display application version metadata")
            sys.exit(0)
    main()
