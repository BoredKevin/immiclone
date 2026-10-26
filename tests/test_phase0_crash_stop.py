import os
import sys
import json
import time
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dashboard.config as config
import dashboard.services.workers as workers_module
import dashboard.services.transactions as tx_module
from dashboard.handlers.base import BaseHandler

class TestPhase0CrashStop(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Cleanup temporary files
        for root, dirs, files in os.walk(self.test_dir, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
        try:
            os.rmdir(self.test_dir)
        except OSError:
            pass

    def test_systemd_rclone_service_configuration(self):
        """Verifies systemd/immiclone-rclone.service uses Type=simple and proper stops."""
        svc_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "systemd", "immiclone-rclone.service"))
        self.assertTrue(os.path.isfile(svc_path), "immiclone-rclone.service missing")
        with open(svc_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Type=simple", content, "immiclone-rclone.service must be Type=simple to avoid 90s notify timeout")
        self.assertNotIn("Type=notify", content)
        self.assertIn("KillMode=mixed", content)
        self.assertIn("TimeoutStopSec=20s", content)

    def test_systemd_dashboard_service_nonblocking_mount(self):
        """Verifies systemd/immiclone.service does not block on immiclone-rclone.service."""
        svc_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "systemd", "immiclone.service"))
        self.assertTrue(os.path.isfile(svc_path), "immiclone.service missing")
        with open(svc_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("After=network.target network-online.target immiclone-rclone.service", content)
        self.assertIn("Wants=network-online.target immiclone-rclone.service", content)

    def test_install_script_mount_check_exit_code(self):
        """Verifies scripts/install.sh does not swallow --mount-check exit codes with || true."""
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "install.sh"))
        self.assertTrue(os.path.isfile(script_path), "install.sh missing")
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("--mount-check 2>/dev/null || true;", content)
        self.assertIn("--mount-check >/dev/null 2>&1; then", content)

    def test_workers_store_corrupt_recovery_and_quarantine(self):
        """Verifies corrupted workers_registry.json is quarantined and does not crash load_workers."""
        fake_store = os.path.join(self.test_dir, "workers_registry.json")
        with open(fake_store, "w", encoding="utf-8") as f:
            f.write("{invalid json syntax: true")

        with patch.object(workers_module, "WORKERS_STORE_PATH", fake_store):
            result = workers_module.load_workers()
            self.assertEqual(result, [])
            # Verify file was quarantined
            self.assertFalse(os.path.exists(fake_store))
            corrupt_files = [fn for fn in os.listdir(self.test_dir) if "corrupt" in fn]
            self.assertTrue(len(corrupt_files) > 0, "Corrupt workers store must be quarantined")

    def test_workers_store_non_list_quarantine(self):
        """Verifies a JSON dict or primitive in workers store is quarantined."""
        fake_store = os.path.join(self.test_dir, "workers_registry.json")
        with open(fake_store, "w", encoding="utf-8") as f:
            f.write(json.dumps({"worker1": {"id": "w1"}}))

        with patch.object(workers_module, "WORKERS_STORE_PATH", fake_store):
            result = workers_module.load_workers()
            self.assertEqual(result, [])
            self.assertFalse(os.path.exists(fake_store))

    def test_init_workers_from_disk_invalid_shapes(self):
        """Verifies init_workers_from_disk safely handles malformed worker objects."""
        malformed_workers = [
            "not a dict",
            {"id": "w1", "last_seen": "invalid_string_timestamp", "token": "tok1"},
            {"id": None, "last_seen": 100},
            {"id": "w2", "last_seen": time.time() - 100, "token": None}
        ]
        with patch.object(workers_module, "load_workers", return_value=malformed_workers):
            with patch.dict(workers_module._active_workers, {}, clear=True):
                with patch.dict(workers_module._worker_tokens, {}, clear=True):
                    workers_module.init_workers_from_disk()
                    # w1 should be marked OFFLINE safely without TypeError
                    self.assertIn("w1", workers_module._active_workers)
                    self.assertEqual(workers_module._active_workers["w1"]["status"], "OFFLINE")
                    self.assertEqual(workers_module._worker_tokens.get("tok1"), "w1")
                    # w2 should also be OFFLINE safely
                    self.assertIn("w2", workers_module._active_workers)
                    self.assertEqual(workers_module._active_workers["w2"]["status"], "OFFLINE")

    def test_transactions_store_corrupt_recovery_and_quarantine(self):
        """Verifies corrupted transactions store is quarantined and returns empty list."""
        fake_store = os.path.join(self.test_dir, "duplication_transactions.json")
        with open(fake_store, "w", encoding="utf-8") as f:
            f.write("corrupted data chunk")

        with patch.object(tx_module, "TX_STORE_PATH", fake_store):
            result = tx_module.load_transactions()
            self.assertEqual(result, [])
            self.assertFalse(os.path.exists(fake_store))
            corrupt_files = [fn for fn in os.listdir(self.test_dir) if "corrupt" in fn]
            self.assertTrue(len(corrupt_files) > 0, "Corrupt transactions store must be quarantined")

    def test_app_config_schema_preserving_save(self):
        """Verifies save_app_config deep-merges partial dictionaries and preserves defaults."""
        fake_store = os.path.join(self.test_dir, "app_config.json")
        with patch.object(config, "APP_CONFIG_PATH", fake_store):
            with patch.object(config, "_cached_config", None):
                # Save partial general config
                config.save_app_config({"general": {"app_name": "Custom Immiclone"}})
                saved = config.get_app_config()
                self.assertEqual(saved["general"]["app_name"], "Custom Immiclone")
                # Storage section must be preserved from DEFAULT_CONFIG
                self.assertIn("storage", saved)
                self.assertIn("primary_remote", saved["storage"])
                self.assertIn("mount_base", saved["storage"])

    def test_read_json_body_safe_length_and_bounds(self):
        """Verifies BaseHandler.read_json_body protects against invalid Content-Length headers."""
        handler = BaseHandler.__new__(BaseHandler)
        # Invalid Content-Length
        handler.headers = {"Content-Length": "not_an_int"}
        handler.rfile = MagicMock()
        self.assertEqual(handler.read_json_body(), {})

        # Oversized Content-Length
        handler.headers = {"Content-Length": "50000000"} # 50 MB > 10 MB limit
        self.assertEqual(handler.read_json_body(), {})

        # Valid JSON body
        valid_json = b'{"hello": "world"}'
        handler.headers = {"Content-Length": str(len(valid_json))}
        handler.rfile.read.return_value = valid_json
        self.assertEqual(handler.read_json_body(), {"hello": "world"})

if __name__ == "__main__":
    unittest.main()
