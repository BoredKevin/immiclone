#!/usr/bin/env python3
import os
import sys
import json
import time
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.services.bandwidth.base import BaseISPProvider, BandwidthSnapshot
from dashboard.services.bandwidth.providers.manual import ManualProvider
from dashboard.services.bandwidth.providers.biznet import BiznetProvider
from dashboard.services.bandwidth.providers import get_provider_classes
from dashboard.services.bandwidth.manager import (
    get_provider_instance,
    get_cached_bandwidth_status,
    load_bandwidth_config,
    save_bandwidth_config,
    mask_bandwidth_config,
    test_provider_connection,
    format_prometheus_metrics
)
from dashboard.handlers.renderer import render_template

class TestModularBandwidthSystem(unittest.TestCase):

    def setUp(self):
        # Reset provider instances before each test
        from dashboard.services.bandwidth.manager import _INSTANCES
        _INSTANCES.clear()

    def test_01_provider_registry_and_contracts(self):
        """Validates that all registered providers adhere to BaseISPProvider."""
        classes = get_provider_classes()
        self.assertIn("biznet", classes)
        self.assertIn("manual", classes)
        self.assertIn("indihome", classes)

        for pid, cls in classes.items():
            self.assertTrue(issubclass(cls, BaseISPProvider))
            schema = cls.get_config_schema()
            self.assertIsInstance(schema, list)
            for field in schema:
                self.assertIn("key", field)
                self.assertIn("label", field)
                self.assertIn("type", field)

    def test_02_manual_provider_telemetry(self):
        """Tests fallback manual provider calculations and reset timestamp."""
        provider = ManualProvider()
        creds = {
            "plan_speed_mbps": 150.0,
            "monthly_quota_gb": 1200.0,
            "quota_remaining_gb": 600.0,
            "reset_day_of_month": 1,
            "last_downtime_reason": "Dying-gasp",
            "last_downtime_sub": "Power loss detected by OLT"
        }
        snapshot = provider.fetch_telemetry(creds)
        self.assertTrue(snapshot.online)
        self.assertEqual(snapshot.plan_speed_mbps, 150.0)
        self.assertEqual(snapshot.quota_limit_bytes, int(1200.0 * (1024 ** 3)))
        self.assertEqual(snapshot.quota_remaining_bytes, int(600.0 * (1024 ** 3)))
        self.assertEqual(snapshot.last_downtime_reason, "Dying-gasp")
        self.assertEqual(snapshot.last_downtime_sub, "Power loss detected by OLT")
        self.assertGreater(snapshot.reset_timestamp, 0)

    def test_03_biznet_provider_mocked_flow(self):
        """Tests BiznetProvider REST sequence (/login -> /getQuota -> /getBandwidth) with token caching."""
        provider = BiznetProvider()
        self.assertEqual(provider.USER_AGENT, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")

        login_resp = json.dumps({"code": 200, "success": True, "api-token": "test-jwt-token-xyz"}).encode("utf-8")
        quota_resp = json.dumps({
            "mainKuota": {
                "remainingLimit": 500.0,  # in GB (< 10M)
                "limit": 1000.0,
                "validUntil": "2026-11-01 00:00:00"
            }
        }).encode("utf-8")
        bw_resp = json.dumps({
            "data": {
                "active": {
                    "bandwidth": 200,
                    "uom": "Mbps"
                }
            }
        }).encode("utf-8")

        mock_responses = [
            BytesIO(login_resp),
            BytesIO(quota_resp),
            BytesIO(bw_resp)
        ]

        def fake_urlopen(req, timeout=10.0):
            # Verify User-Agent
            self.assertEqual(req.headers.get("User-agent"), provider.USER_AGENT)
            m = MagicMock()
            resp_bytes = mock_responses.pop(0)
            m.read.return_value = resp_bytes.getvalue()
            m.__enter__.return_value = m
            return m

        creds = {"biznet_id": "000000123456", "username": "testuser", "password": "secretpassword"}

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            snap = provider.fetch_telemetry(creds)
            self.assertTrue(snap.online)
            self.assertEqual(snap.plan_speed_mbps, 200.0)
            self.assertEqual(snap.quota_limit_bytes, int(1000.0 * (1024 ** 3)))
            self.assertEqual(snap.quota_remaining_bytes, int(500.0 * (1024 ** 3)))
            self.assertEqual(snap.last_downtime_reason, "Dying-gasp")
            self.assertGreater(snap.reset_timestamp, 0)
            self.assertEqual(provider._cached_token, "test-jwt-token-xyz")

    def test_04_singleton_persistence_in_manager(self):
        """Verifies that manager.py reuses the same singleton provider instance across cycles."""
        inst1 = get_provider_instance("biznet")
        inst1._cached_token = "persistent-token"
        inst1._token_expires_at = time.time() + 3600

        inst2 = get_provider_instance("biznet")
        self.assertIs(inst1, inst2)
        self.assertEqual(inst2._cached_token, "persistent-token")

    def test_05_line_saturation_and_status(self):
        """Tests live upload line saturation calculations."""
        # 12.5 MB/s = 100 Mbps on a 100 Mbps plan = 100% saturation
        bps = 12.5 * 1024 * 1024
        status = get_cached_bandwidth_status(live_upload_bps=bps)

        self.assertIn("saturation_pct", status)
        self.assertIn("live_speed_mbps", status)
        self.assertIn("quota", status)
        self.assertIn("downtime", status)
        self.assertGreater(status["saturation_pct"], 90.0)

    def test_06_password_masking_and_preservation(self):
        """Verifies that masked placeholders ('••••••••') preserve the existing stored password."""
        initial_cfg = {
            "enabled": True,
            "active_provider": "biznet",
            "poll_interval_seconds": 300,
            "providers": {
                "biznet": {
                    "biznet_id": "0000111",
                    "username": "kevin",
                    "password": "supersecretpassword123"
                }
            }
        }
        save_bandwidth_config(initial_cfg)

        # Client loads config (receives masked password)
        masked = mask_bandwidth_config(load_bandwidth_config())
        self.assertEqual(masked["providers"]["biznet"]["password"], "••••••••")

        # Client submits update keeping masked password
        updated_submission = {
            "enabled": True,
            "active_provider": "biznet",
            "poll_interval_seconds": 600,
            "providers": {
                "biznet": {
                    "biznet_id": "0000111",
                    "username": "kevin",
                    "password": "••••••••"  # Masked placeholder
                }
            }
        }
        save_bandwidth_config(updated_submission)

        # Loaded config must still retain the real secret password
        reloaded = load_bandwidth_config()
        self.assertEqual(reloaded["providers"]["biznet"]["password"], "supersecretpassword123")
        self.assertEqual(reloaded["poll_interval_seconds"], 600)

    def test_07_prometheus_metrics_export(self):
        """Verifies GET /api/v1/bandwidth/metrics output format."""
        prom_text = format_prometheus_metrics()
        self.assertIn("# HELP immiclone_bandwidth_plan_speed_mbps", prom_text)
        self.assertIn("# TYPE immiclone_bandwidth_plan_speed_mbps gauge", prom_text)
        self.assertIn("# HELP immiclone_bandwidth_quota_remaining_bytes", prom_text)
        self.assertIn("immiclone_bandwidth_downtime_info", prom_text)

    def test_08_template_and_split_layout_rendering(self):
        """Verifies template compiles and contains 50/50 split layout and new bandwidth cards."""
        html = render_template("index.html")
        self.assertIn('class="active-transfers-split-grid"', html)
        self.assertIn('id="active-transfers-split-container"', html)
        self.assertIn('id="pinned-uploads-section"', html)
        self.assertIn('id="bandwidth-monitor-section"', html)
        self.assertIn('id="modal-bandwidth"', html)
        self.assertIn('id="header-bw-pill"', html)
        self.assertIn('id="bw-downtime-reason"', html)
        self.assertIn('id="bw-quota-remaining"', html)
        self.assertIn('id="bw-saturation-val"', html)

if __name__ == "__main__":
    unittest.main()
