import os
import sys
import time
import json
import socket
import re
import urllib.request
import subprocess
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from dashboard.handlers.renderer import render_template, _TEMPLATE_CACHE

TEST_PORT = 8096

def wait_for_port(port, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.1)
    return False

class TestImmicloneDesignSystemAndUI(unittest.TestCase):
    """Test suite validating the Linear/Vercel/Raycast design systems, template renderer, and frontend architecture."""

    def test_css_design_system_integrity(self):
        css_path = os.path.join(REPO_DIR, "dashboard", "static", "css", "style.css")
        self.assertTrue(os.path.exists(css_path), "style.css must exist")
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()

        # 1. Canvas Palette & Specular Highlighting
        self.assertIn("#08090c", css, "Deep obsidian background (#08090c) missing")
        self.assertIn("--border-specular", css, "Specular highlight border variable missing")
        self.assertIn("border-top-color", css, "Specular border-top-color missing")

        # 2. Recessed Wells
        self.assertIn(".tx-details-well", css, "Recessed metadata well missing")
        self.assertIn("box-shadow: inset 0 1px", css, "Recessed inner shadows missing")

        # 3. Tabular numbers & monospace
        self.assertIn("font-variant-numeric: tabular-nums", css, "Tabular nums discipline missing")
        self.assertIn(".flag-pill", css, "CLI micro-pills class missing")

        # 4. Unified 3-tier buttons
        self.assertIn(".btn-primary", css, "Primary button class missing")
        self.assertIn(".btn-danger", css, "Destructive button class missing")
        self.assertIn("#f87171", css, "Hover crimson text color for destructive buttons missing")

        # 5. Segmented Navigation Track
        self.assertIn(".nav-tabs", css, "Segmented control track missing")

        # 6. Micro-Interactions & Shimmer
        self.assertIn("@keyframes pulse-bar", css, "Active pulse bar shimmer keyframes missing")
        self.assertIn(".status-dot", css, "Clean 6px glowing status dots missing")

        # 7. Declarative Utility
        self.assertRegex(css, r'\.hidden\s*\{\s*display:\s*none\s*!important;\s*\}', ".hidden utility class missing in style.css")

    def test_html_template_stitching_and_partials(self):
        # 1. Master index.html must use modular partial includes
        index_raw_path = os.path.join(REPO_DIR, "dashboard", "templates", "index.html")
        self.assertTrue(os.path.exists(index_raw_path), "index.html must exist")
        with open(index_raw_path, "r", encoding="utf-8") as f:
            raw_index = f.read()
        self.assertIn("<!-- include: partials/header.html -->", raw_index)
        self.assertIn("<!-- include: partials/tab_duplication.html -->", raw_index)
        self.assertIn('<script type="module" src="/static/js/app.js"></script>', raw_index)

        # 2. Rendered template assembly
        rendered = render_template("index.html")
        self.assertNotIn("<!-- Missing partial", rendered, "Rendered HTML contains missing partial comment")
        self.assertNotIn("<!-- Template not found", rendered, "Template not found")
        self.assertTrue(len(rendered) > 15000, f"Rendered HTML too short ({len(rendered)} chars)")

        # 3. Kill native OS emojis
        for emoji in ["🚀", "🔒", "🔄", "🗑️", "✏️", "🧹", "📁", "⚡", "💾", "📸"]:
            self.assertNotIn(emoji, rendered, f"Native OS emoji '{emoji}' was found in rendered HTML")

        # 4. Inline SVG icons
        self.assertIn("<svg class=\"icon", rendered, "Inline SVG icons missing in rendered HTML")

        # 5. Consolidated Top Bar & Subtitle SemVer Indicator
        self.assertIn("brand-version", rendered, "Clickable Version in brand subtitle missing")
        self.assertIn("header-poll-pill", rendered, "Polling interval status pill missing")
        self.assertIn("poll-interval-select", rendered, "Poll frequency dropdown selector missing")
        self.assertIn("header-ts-pill", rendered, "Clickable Tailscale header pill missing")
        self.assertIn("header-ts-dot", rendered, "Tailscale status dot missing")
        self.assertIn("header-divider", rendered, "Visual divider separating badges and buttons missing")
        self.assertIn("btn-header", rendered, "Elevated action button styling missing")
        self.assertIn('data-action="open-modal"', rendered, "Declarative modal trigger missing")

        # 5b. Mount KPI Cards Micro-Visuals & Transfers Table Structure
        self.assertIn("speed-sparkline", rendered, "Bandwidth sparkline SVG container missing")
        self.assertIn("stat-rc-queue", rendered, "Queue depth indicator missing")
        self.assertIn("stat-rc-remaining", rendered, "Queue remaining bytes context missing")
        self.assertIn("stat-rc-committed", rendered, "Committed transfers counter missing")
        self.assertIn("stat-rc-failed", rendered, "Failed transfers counter missing")
        self.assertIn("transfers-view-toggle", rendered, "Transfers segmented control missing")
        self.assertIn("btn-toggle-pause", rendered, "Global mount pause toggle button missing")
        self.assertNotIn("<th>Transferred</th>", rendered, "Redundant Transferred column should be eliminated")

        # 6. Queued Transaction Filter
        self.assertIn("tx-filter-queued", rendered, "Queued transaction filter pill missing")
        self.assertIn("count-tx-queued", rendered, "Queued count badge missing")

        # 7. Single-line Terminal Bar
        self.assertIn("terminal-bar", rendered, "Sleek terminal command bar missing")
        self.assertIn("worker-cmd-display", rendered, "Worker command display missing")

        # 8. Multi-Cloud & Host Storage Matrix
        self.assertIn("cloud-remotes-grid", rendered, "Dynamic cloud remotes grid container missing")
        self.assertIn("Local Host Storage Matrix", rendered, "Host storage matrix missing")

        # 9. Modals (including updates modal)
        self.assertIn("modal-tailscale", rendered, "Tailscale modal missing")
        self.assertIn("modal-new-tx", rendered, "New transaction modal missing")
        self.assertIn("modal-edit-tx", rendered, "Edit transaction modal missing")
        self.assertIn("modal-worker", rendered, "Worker modal missing")
        self.assertIn("modal-settings", rendered, "Settings modal missing")
        self.assertIn("modal-updates", rendered, "Updates modal missing")

        # 10. Declarative HTML5 <template> tags (Templates Engine)
        self.assertIn('<template id="tpl-tx-card">', rendered, "tpl-tx-card template missing")
        self.assertIn('<template id="tpl-worker-row">', rendered, "tpl-worker-row template missing")
        self.assertIn('<template id="tpl-media-row">', rendered, "tpl-media-row template missing")
        self.assertIn('<template id="tpl-job-row">', rendered, "tpl-job-row template missing")
        self.assertIn('<template id="tpl-remote-card">', rendered, "tpl-remote-card template missing")

        # Rule 1 verification: Action buttons and worker <select> directly inside #tpl-tx-card
        self.assertIn('data-bind="actions-running"', rendered, "actions-running group missing in #tpl-tx-card")
        self.assertIn('data-bind="actions-pending"', rendered, "actions-pending group missing in #tpl-tx-card")
        self.assertIn('data-bind="actions-completed"', rendered, "actions-completed group missing in #tpl-tx-card")
        self.assertIn('data-bind="assign-select"', rendered, "assign-select missing in #tpl-tx-card")

    def test_renderer_mtime_caching(self):
        # Initial render populates cache
        html1 = render_template("index.html")
        cached_mtime = _TEMPLATE_CACHE["mtime"]
        self.assertTrue(cached_mtime > 0)
        self.assertEqual(html1, _TEMPLATE_CACHE["html"])

        # Second render hits cache
        html2 = render_template("index.html")
        self.assertIs(html1, html2)

    def test_es_modules_and_architecture_rules(self):
        modules_dir = os.path.join(REPO_DIR, "dashboard", "static", "js", "modules")
        expected_modules = [
            "api.js", "dom.js", "duplication.js", "events.js", "formatters.js",
            "icons.js", "media.js", "modals.js", "mount.js", "sse.js", "storage.js", "updater.js"
        ]
        for mod in expected_modules:
            mod_path = os.path.join(modules_dir, mod)
            self.assertTrue(os.path.exists(mod_path), f"Module {mod} missing from modules directory")

        # Rule 2: dom.js must use WeakMap for element binding cache
        dom_js_path = os.path.join(modules_dir, "dom.js")
        with open(dom_js_path, "r", encoding="utf-8") as f:
            dom_js = f.read()
        self.assertIn("elementBindCache = new WeakMap()", dom_js, "dom.js must use WeakMap caching per Rule 2")
        self.assertIn("function reconcileList", dom_js, "dom.js must export reconcileList")

        # Rule 3: events.js must fall back to target.closest('[data-key]')?.dataset.key
        events_js_path = os.path.join(modules_dir, "events.js")
        with open(events_js_path, "r", encoding="utf-8") as f:
            events_js = f.read()
        self.assertIn("closest('[data-key]')", events_js, "events.js must check closest('[data-key]') per Rule 3")
        self.assertIn("data.id = keyEl.dataset.key", events_js, "events.js must fallback dataset.id per Rule 3")

        # Rule 1: duplication.js must toggle action visibility using .hidden
        dup_js_path = os.path.join(modules_dir, "duplication.js")
        with open(dup_js_path, "r", encoding="utf-8") as f:
            dup_js = f.read()
        self.assertIn("bindHidden(el, 'actions-running'", dup_js, "duplication.js must toggle actions-running per Rule 1")
        self.assertIn("bindHidden(el, 'actions-pending'", dup_js, "duplication.js must toggle actions-pending per Rule 1")
        self.assertIn("bindHidden(el, 'actions-completed'", dup_js, "duplication.js must toggle actions-completed per Rule 1")
        self.assertIn("optionsSig", dup_js, "duplication.js must preserve assign-select options focus/selection")

        # Check mount.js for prefix stripping and finalizing state
        mount_js_path = os.path.join(modules_dir, "mount.js")
        with open(mount_js_path, "r", encoding="utf-8") as f:
            mount_js = f.read()
        self.assertIn("replace(/^library\\/library\\//", mount_js, "mount.js must strip double prefix")
        self.assertIn("Finalizing / Verifying...", mount_js, "mount.js must display finalizing state")

        # Check formatters.js
        fmt_js_path = os.path.join(modules_dir, "formatters.js")
        with open(fmt_js_path, "r", encoding="utf-8") as f:
            fmt_js = f.read()
        self.assertIn("formatRelativeTime", fmt_js)
        self.assertIn("populateFlagPills", fmt_js)
        self.assertIn("maskCommandSecret", fmt_js)

        # Check app.js is a modular entry point
        app_js_path = os.path.join(REPO_DIR, "dashboard", "static", "js", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("import { initEventDelegation", app_js)
        self.assertIn("registerAction('switch-tab'", app_js)
        self.assertIn("registerAction('assign-tx'", app_js)
        self.assertIn("registerAction('open-modal'", app_js)
        self.assertIn("registerAction('check-updates'", app_js)
        self.assertIn("registerChange('toggle-auto-ts'", app_js)


class TestLiveDashboardServer(unittest.TestCase):
    """End-to-end integration tests on running ThreadedHTTPServer with modular API v1 architecture."""

    @classmethod
    def setUpClass(cls):
        cls.env = os.environ.copy()
        cls.env["PORT"] = str(TEST_PORT)
        cls.env["DATA_DIR"] = os.path.join(REPO_DIR, "test_ui_data_dir")
        os.makedirs(cls.env["DATA_DIR"], exist_ok=True)

        server_script = os.path.join(REPO_DIR, "dashboard", "server.py")
        cls.proc = subprocess.Popen([sys.executable, server_script], env=cls.env)
        if not wait_for_port(TEST_PORT, timeout=5):
            cls.proc.kill()
            raise RuntimeError(f"Server failed to launch on port {TEST_PORT}")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        import shutil
        shutil.rmtree(os.path.join(REPO_DIR, "test_ui_data_dir"), ignore_errors=True)

    def test_get_root_html(self):
        url = f"http://127.0.0.1:{TEST_PORT}/"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("<!DOCTYPE html>", body)
            self.assertIn("Immiclone", body)
            self.assertIn("/static/css/style.css", body)
            self.assertIn('<script type="module" src="/static/js/app.js"></script>', body)
            self.assertIn('<template id="tpl-tx-card">', body)

    def test_get_static_css_and_es_modules(self):
        # 1. CSS
        url_css = f"http://127.0.0.1:{TEST_PORT}/static/css/style.css"
        with urllib.request.urlopen(url_css, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "text/css; charset=utf-8")
            css_bytes = resp.read()
            self.assertIn(b"--bg: #08090c;", css_bytes)
            self.assertIn(b".hidden", css_bytes)

        # 2. Main Entry Point JS
        url_js = f"http://127.0.0.1:{TEST_PORT}/static/js/app.js"
        with urllib.request.urlopen(url_js, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "application/javascript; charset=utf-8")
            js_bytes = resp.read()
            self.assertIn(b"initEventDelegation", js_bytes)

        # 3. ES Modules
        modules = ["dom.js", "events.js", "duplication.js", "media.js", "mount.js", "storage.js", "modals.js", "sse.js", "updater.js"]
        for mod in modules:
            url_mod = f"http://127.0.0.1:{TEST_PORT}/static/js/modules/{mod}"
            with urllib.request.urlopen(url_mod, timeout=3) as resp:
                self.assertEqual(resp.status, 200, f"Failed to fetch module {mod}")
                self.assertEqual(resp.headers.get("Content-Type"), "application/javascript; charset=utf-8")
                mod_bytes = resp.read()
                self.assertTrue(len(mod_bytes) > 50, f"Module {mod} empty or truncated")

    def test_api_v1_version_and_updates(self):
        # 1. Canonical /api/v1/version
        url_ver = f"http://127.0.0.1:{TEST_PORT}/api/v1/version"
        with urllib.request.urlopen(url_ver, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("version"), "1.0.1")
            self.assertEqual(data.get("api_version"), "v1")
            self.assertIn("semver", data)
            self.assertEqual(data["semver"]["major"], 1)
            self.assertEqual(data["semver"]["minor"], 0)
            self.assertEqual(data["semver"]["patch"], 1)
            self.assertIn("git", data)

        # 2. Canonical /api/v1/updates
        url_upd = f"http://127.0.0.1:{TEST_PORT}/api/v1/updates"
        with urllib.request.urlopen(url_upd, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("status", data)
            self.assertIn("update_available", data)

        # 3. POST /api/v1/updates/check
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/v1/updates/check",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("status", data)
            self.assertIn("update_available", data)

    def test_backward_compatibility_aliasing(self):
        # Verify legacy /api/settings maps seamlessly to /api/v1/settings
        url_legacy = f"http://127.0.0.1:{TEST_PORT}/api/settings"
        url_canonical = f"http://127.0.0.1:{TEST_PORT}/api/v1/settings"

        with urllib.request.urlopen(url_legacy, timeout=3) as resp1:
            data_legacy = json.loads(resp1.read().decode("utf-8"))

        with urllib.request.urlopen(url_canonical, timeout=3) as resp2:
            data_canonical = json.loads(resp2.read().decode("utf-8"))

        self.assertEqual(data_legacy.keys(), data_canonical.keys())
        self.assertEqual(data_legacy.get("storage"), data_canonical.get("storage"))

        # Verify legacy /api/version works
        url_ver_legacy = f"http://127.0.0.1:{TEST_PORT}/api/version"
        with urllib.request.urlopen(url_ver_legacy, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("version"), "1.0.1")

    def test_get_api_v1_media(self):
        url = f"http://127.0.0.1:{TEST_PORT}/api/v1/media?page=1&limit=10"
        with urllib.request.urlopen(url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("page", data)
            self.assertIn("total_files", data)
            self.assertIn("files", data)

    def test_get_worker_script_zero_cdn(self):
        url = f"http://127.0.0.1:{TEST_PORT}/worker.sh"
        with urllib.request.urlopen(url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read()
            self.assertTrue(body.startswith(b"#!/usr/bin/env bash"))

        url_stable = f"http://127.0.0.1:{TEST_PORT}/worker-stable.sh"
        with urllib.request.urlopen(url_stable, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            body_stable = resp.read()
            self.assertTrue(body_stable.startswith(b"#!/usr/bin/env bash"))

    def test_worker_create_session_stable_link(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/v1/worker/create-session",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("one_liner", data)
            self.assertIn("worker-stable.sh", data["one_liner"])
            self.assertIn("https://raw.githubusercontent.com/BoredKevin/immiclone", data["one_liner"])

    def test_rclone_throttle_api(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/v1/rclone/throttle",
            data=json.dumps({"rate": "10M"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("rate"), "10M")

if __name__ == "__main__":
    unittest.main()
