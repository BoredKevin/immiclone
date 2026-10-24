import os
import json
import re
import http.server
from dashboard.config import STATIC_DIR, TEMPLATES_DIR
from dashboard.handlers.renderer import render_template

class BaseHandler(http.server.BaseHTTPRequestHandler):
    """Base HTTP Request Handler with response helpers and path-traversal guarded static delivery."""

    def normalize_api_path(self, path):
        """Rewrites legacy /api/<path> to canonical /api/v1/<path> transparently."""
        if path.startswith("/api/") and not re.match(r"^/api/v\d+(/|$)", path):
            return "/api/v1" + path[len("/api"):]
        return path

    def send_json(self, data, status=200):
        """Sends a JSON response with status code."""
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, content, content_type="text/plain; charset=utf-8", status=200):
        """Sends a text/html response."""
        payload = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_error_msg(self, status=400, message="Bad Request"):
        """Sends an error response."""
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))

    def read_json_body(self):
        """Parses JSON body from incoming POST request."""
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            body = self.rfile.read(length).decode("utf-8")
            return json.loads(body)
        except Exception:
            return {}

    def serve_static(self, rel_path):
        """Delivers static assets with canonical path traversal prevention."""
        real_static = os.path.realpath(STATIC_DIR)
        clean_rel = rel_path.lstrip("/\\")
        target_path = os.path.realpath(os.path.join(real_static, clean_rel))

        # Security: Prevent ../ escape from STATIC_DIR
        if not target_path.startswith(real_static + os.sep) or not os.path.isfile(target_path):
            self.send_error_msg(403, "Forbidden")
            return

        # Determine MIME type
        content_type = "application/octet-stream"
        if target_path.endswith(".css"):
            content_type = "text/css; charset=utf-8"
        elif target_path.endswith(".js"):
            content_type = "application/javascript; charset=utf-8"
        elif target_path.endswith(".png"):
            content_type = "image/png"
        elif target_path.endswith(".svg"):
            content_type = "image/svg+xml"
        elif target_path.endswith(".ico"):
            content_type = "image/x-icon"

        try:
            with open(target_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            print(f"[!] Error serving static file: {e}")
            self.send_error_msg(500, "Internal Server Error")

    def serve_index(self):
        """Serves index.html with recursive partials assembled and cached."""
        content = render_template("index.html")
        if content and not content.startswith("<!-- Template not found"):
            self.send_text(content, content_type="text/html; charset=utf-8")
        else:
            self.send_error_msg(404, "Index template not found")

    def log_message(self, format, *args):
        """Suppresses default HTTP server stdout logging for clean logs."""
        pass
