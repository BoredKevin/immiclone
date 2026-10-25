import time
from typing import Dict, Any, List
from dashboard.services.bandwidth.base import BaseISPProvider, BandwidthSnapshot

class IndiHomeProvider(BaseISPProvider):
    provider_id = "indihome"
    display_name = "Telkom IndiHome (Coming Soon)"

    @classmethod
    def get_config_schema(cls) -> List[Dict[str, Any]]:
        return [
            {"key": "account_number", "label": "IndiHome Internet Number", "type": "text", "placeholder": "12xxxxxxxxxx"},
            {"key": "phone_or_email", "label": "MyIndiHome Phone / Email", "type": "text", "placeholder": "0812xxxxxxxx"}
        ]

    def fetch_telemetry(self, credentials: Dict[str, Any]) -> BandwidthSnapshot:
        return BandwidthSnapshot(
            provider_id=self.provider_id,
            provider_name=self.display_name,
            online=False,
            plan_speed_mbps=50.0,
            quota_remaining_bytes=0,
            quota_limit_bytes=0,
            reset_timestamp=0,
            last_downtime_reason="Provider Stub",
            last_downtime_sub="IndiHome provider support is under development",
            fetched_at=time.time(),
            error_message="Provider driver not yet active"
        )
