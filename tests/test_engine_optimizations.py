import os
import sys
import time
import json
import unittest
from unittest.mock import patch, MagicMock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from dashboard.config import get_primary_remote, format_size
from dashboard.services.scanner import (
    fetch_cloud_quota,
    get_cached_cloud_quota,
    _cloud_quota_cache,
    _quota_lock,
    get_live_sse_payload
)
from dashboard.services.transactions import (
    DEFAULT_RCLONE_FLAGS,
    sanitize_rclone_flags,
    parse_remote_name,
    resolve_remote_info,
    check_cross_drive_sharing,
    create_transaction,
    record_worker_telemetry,
    get_transaction_by_id
)

class TestAuthoritativeCloudQuota(unittest.TestCase):
    """Tests for cached quota manager, non-blocking SSE telemetry, and real quota parsing."""

    def setUp(self):
        with _quota_lock:
            _cloud_quota_cache["remote"] = None
            _cloud_quota_cache["raw"] = {"total": 0, "used": 0, "free": 0, "trashed": 0}
            _cloud_quota_cache["data"] = {
                "remote": "",
                "total": "0 B",
                "used": "0 B",
                "free": "0 B",
                "trashed": "0 B",
                "percent_used": 0.0
            }
            _cloud_quota_cache["last_updated"] = 0
            _cloud_quota_cache["is_updating"] = False

    @patch("dashboard.services.scanner.query_rclone")
    def test_fetch_cloud_quota_real_values(self, mock_rc):
        # Mock operations/about response matching actual Google Drive / bkc: quota
        mock_rc.return_value = {
            "total": 5497558138880,  # ~5.0 TB
            "used": 146183170103,    # ~146 GB (136.1 GiB)
            "free": 5351372639589,   # ~4.86 TB
            "trashed": 0
        }

        quota = fetch_cloud_quota("bkc:", timeout=5.0)
        self.assertEqual(quota["remote"], "bkc:")
        self.assertEqual(quota["total"], "5.0 TB")
        self.assertIn("GB", quota["used"])
        self.assertGreater(quota["raw"]["used"], 100 * 1024**3)
        self.assertEqual(quota["percent_used"], 2.7)

    @patch("dashboard.services.scanner.query_rclone")
    def test_get_cached_cloud_quota_non_blocking_and_async_update(self, mock_rc):
        mock_rc.return_value = {
            "total": 5497558138880,
            "used": 146183170103,
            "free": 5351372639589,
            "trashed": 0
        }

        # Initial call should return immediately without blocking
        t0 = time.time()
        initial = get_cached_cloud_quota("bkc:", max_age=120)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 0.1, "Initial call must return in <100ms")
        self.assertEqual(initial["remote"], "bkc:")

        # Wait briefly for background daemon thread to finish
        for _ in range(20):
            time.sleep(0.05)
            updated = get_cached_cloud_quota("bkc:", max_age=120)
            if updated["total"] == "5.0 TB":
                break

        self.assertEqual(updated["total"], "5.0 TB")
        self.assertEqual(updated["percent_used"], 2.7)

    @patch("dashboard.services.scanner.query_rclone")
    def test_cached_cloud_quota_respects_ttl(self, mock_rc):
        mock_rc.return_value = {
            "total": 5497558138880,
            "used": 146183170103,
            "free": 5351372639589,
            "trashed": 0
        }

        # Synchronous initial fetch
        quota1 = get_cached_cloud_quota("bkc:", max_age=120, allow_blocking_initial=True)
        self.assertEqual(quota1["total"], "5.0 TB")
        call_count_1 = mock_rc.call_count

        # Second call within TTL should return cached value without querying again
        quota2 = get_cached_cloud_quota("bkc:", max_age=120)
        self.assertEqual(quota2["total"], "5.0 TB")
        self.assertEqual(mock_rc.call_count, call_count_1)


class TestRcloneFlagsAndWorkerOptimization(unittest.TestCase):
    """Tests for gigabit Cloud Shell default flags and --fast-list stripping."""

    def test_default_rclone_flags_contents(self):
        self.assertIn("--drive-chunk-size=64M", DEFAULT_RCLONE_FLAGS)
        self.assertIn("--drive-upload-cutoff=64M", DEFAULT_RCLONE_FLAGS)
        self.assertIn("--buffer-size=32M", DEFAULT_RCLONE_FLAGS)
        self.assertIn("--transfers=4", DEFAULT_RCLONE_FLAGS)
        self.assertIn("--checkers=8", DEFAULT_RCLONE_FLAGS)
        self.assertIn("--tpslimit=10", DEFAULT_RCLONE_FLAGS)
        self.assertIn("--drive-pacer-min-sleep=10ms", DEFAULT_RCLONE_FLAGS)
        self.assertNotIn("--fast-list", DEFAULT_RCLONE_FLAGS)

    def test_sanitize_rclone_flags_strips_fast_list_on_google_drive(self):
        user_flags = ["--size-only", "--fast-list", "--transfers=8"]
        sanitized = sanitize_rclone_flags(user_flags, is_google_drive=True)
        self.assertNotIn("--fast-list", sanitized)
        self.assertIn("--size-only", sanitized)
        self.assertIn("--transfers=8", sanitized)

    def test_sanitize_rclone_flags_keeps_fast_list_for_non_drive(self):
        user_flags = ["--size-only", "--fast-list"]
        sanitized = sanitize_rclone_flags(user_flags, is_google_drive=False)
        self.assertIn("--fast-list", sanitized)


class TestCrossDriveCopyValidationAnd404(unittest.TestCase):
    """Tests for cross-account Drive copy validation and worker 404 detection."""

    def test_parse_remote_name(self):
        self.assertEqual(parse_remote_name("bkc:library/media"), "bkc")
        self.assertEqual(parse_remote_name("1qc:"), "1qc")
        self.assertEqual(parse_remote_name("/mnt/local/media"), "")

    def test_check_cross_drive_sharing_detection(self):
        # bkc: (boredkevinmedia) -> 1qc: (1337quota)
        res = check_cross_drive_sharing(
            source="bkc:library",
            dest="1qc:backup",
            rclone_flags=["--drive-server-side-across-configs"]
        )
        self.assertTrue(res["is_cross_account"])
        self.assertTrue(res["is_src_drive"])
        self.assertTrue(res["is_dst_drive"])
        self.assertEqual(res["status"], "warning")
        self.assertIsNotNone(res["warning"])
        self.assertIn("404 notFound", res["warning"])
        self.assertIn("destination account", res["advice"].lower())

    def test_create_transaction_with_preflight_validation(self):
        tx = create_transaction(
            source="bkc:library",
            dest="1qc:backup",
            title="Cross-Account Replication",
            rclone_flags=["--drive-server-side-across-configs", "--fast-list"]
        )
        self.assertIn("--drive-server-side-across-configs", tx["rclone_flags"])
        # --fast-list should have been stripped automatically
        self.assertNotIn("--fast-list", tx["rclone_flags"])
        self.assertIn("preflight", tx)
        self.assertTrue(tx["preflight"]["is_cross_account"])
        self.assertIn("[Notice]", tx["notes"])

    def test_record_worker_telemetry_handles_failed_status_and_stops_retries(self):
        tx = create_transaction(
            source="bkc:library",
            dest="1qc:backup"
        )
        tx_id = tx["tx_id"]
        lease = tx["lease_id"]

        # Worker reports 404 cross-account error
        code, resp = record_worker_telemetry("worker-test", tx_id, lease, {
            "status": "FAILED",
            "error_message": "Google Drive 404 Not Found: destination account lacks read permissions"
        })
        self.assertEqual(code, 200)
        self.assertEqual(resp["state"], "FAILED")

        updated_tx = get_transaction_by_id(tx_id)
        self.assertEqual(updated_tx["status"], "FAILED")
        self.assertIn("Failed:", updated_tx["current_file"])
        self.assertIsNone(updated_tx["assigned_worker"])

    def test_record_worker_telemetry_handles_interrupted(self):
        tx = create_transaction(source="bkc:library", dest="1qc:backup")
        tx_id = tx["tx_id"]
        lease = tx["lease_id"]

        code, resp = record_worker_telemetry("worker-test", tx_id, lease, {
            "status": "INTERRUPTED",
            "error_message": "Process killed"
        })
        self.assertEqual(code, 200)
        self.assertEqual(resp["state"], "PAUSED")

        updated_tx = get_transaction_by_id(tx_id)
        self.assertEqual(updated_tx["status"], "PAUSED")


if __name__ == "__main__":
    unittest.main()
