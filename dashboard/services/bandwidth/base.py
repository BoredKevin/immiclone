from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class BandwidthSnapshot:
    provider_id: str          # e.g., "biznet", "manual"
    provider_name: str        # e.g., "Biznet Home", "Manual / Custom ISP"
    online: bool              # True if API / connection is reachable
    plan_speed_mbps: float    # e.g., 100.0
    quota_remaining_bytes: int
    quota_limit_bytes: int
    reset_timestamp: int      # Unix epoch for quota renewal (validUntil)
    last_downtime_reason: str # e.g., "Dying-gasp", "LOS (Fiber Cut)", "Normal"
    last_downtime_sub: str    # e.g., "Power loss detected by OLT"
    fetched_at: float         # time.time()
    error_message: str = ""   # Error details if online is False

class BaseISPProvider(ABC):
    provider_id: str = ""
    display_name: str = ""

    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> List[Dict[str, Any]]:
        """Returns form field definitions for dynamic Settings Modal rendering."""
        pass

    @abstractmethod
    def fetch_telemetry(self, credentials: Dict[str, Any]) -> BandwidthSnapshot:
        """Executes pure-Python HTTP requests and returns normalized telemetry."""
        pass
