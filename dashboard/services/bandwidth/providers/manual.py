import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from dashboard.services.bandwidth.base import BaseISPProvider, BandwidthSnapshot

class ManualProvider(BaseISPProvider):
    provider_id = "manual"
    display_name = "Manual / Custom ISP"

    @classmethod
    def get_config_schema(cls) -> List[Dict[str, Any]]:
        return [
            {"key": "plan_speed_mbps", "label": "Plan Speed (Mbps)", "type": "number", "placeholder": "100"},
            {"key": "monthly_quota_gb", "label": "Monthly Quota Limit (GB)", "type": "number", "placeholder": "1000"},
            {"key": "quota_remaining_gb", "label": "Quota Remaining (GB)", "type": "number", "placeholder": "450"},
            {"key": "reset_day_of_month", "label": "Quota Reset Day of Month", "type": "number", "placeholder": "1"},
            {"key": "last_downtime_reason", "label": "Last Downtime Reason", "type": "text", "placeholder": "Dying-gasp"},
            {"key": "last_downtime_sub", "label": "Downtime Description", "type": "text", "placeholder": "Power loss detected by OLT"}
        ]

    def fetch_telemetry(self, credentials: Dict[str, Any]) -> BandwidthSnapshot:
        try:
            plan_speed = float(credentials.get("plan_speed_mbps", 100.0) or 100.0)
        except (ValueError, TypeError):
            plan_speed = 100.0

        try:
            quota_gb = float(credentials.get("monthly_quota_gb", 1000.0) or 1000.0)
        except (ValueError, TypeError):
            quota_gb = 1000.0

        try:
            rem_gb = float(credentials.get("quota_remaining_gb", 450.0) or 450.0)
        except (ValueError, TypeError):
            rem_gb = 450.0

        reason = str(credentials.get("last_downtime_reason") or "Dying-gasp").strip()
        sub = str(credentials.get("last_downtime_sub") or "Power loss detected by OLT").strip()

        # Compute reset timestamp
        try:
            reset_day = int(credentials.get("reset_day_of_month", 1) or 1)
            now = datetime.now()
            # Calculate next reset day
            year = now.year
            month = now.month
            if now.day >= reset_day:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            reset_dt = datetime(year, month, min(reset_day, 28), 0, 0, 0)
            reset_ts = int(reset_dt.timestamp())
        except Exception:
            reset_ts = int(time.time() + 86400 * 6)

        return BandwidthSnapshot(
            provider_id=self.provider_id,
            provider_name=self.display_name,
            online=True,
            plan_speed_mbps=plan_speed,
            quota_remaining_bytes=int(rem_gb * (1024 ** 3)),
            quota_limit_bytes=int(quota_gb * (1024 ** 3)),
            reset_timestamp=reset_ts,
            last_downtime_reason=reason,
            last_downtime_sub=sub,
            fetched_at=time.time(),
            error_message="",
            last_downtime_time="",
            last_uptime_time="",
            router_run_state="Online",
            modem_status="Active",
            device_name="Manual Gateway",
            optical_rx_power="",
            optical_tx_power="",
            optical_attenuation="N/A (Manual Plan)"
        )
