import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, List
from dashboard.services.bandwidth.base import BaseISPProvider, BandwidthSnapshot

class BiznetProvider(BaseISPProvider):
    provider_id = "biznet"
    display_name = "Biznet Home"

    API_BASE = "https://mybiznet.biznetform.com/api"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"

    def __init__(self):
        self._cached_token = None
        self._token_expires_at = 0.0

    @classmethod
    def get_config_schema(cls) -> List[Dict[str, Any]]:
        return [
            {"key": "biznet_id", "label": "Customer / Contract Number", "type": "text", "placeholder": "000000xxxxxx"},
            {"key": "username", "label": "Biznet Username / Email", "type": "text", "placeholder": "user@example.com"},
            {"key": "password", "label": "Biznet Password", "type": "password", "placeholder": "••••••••"},
            {"key": "bearer_token", "label": "Bearer Token (Authorization Header)", "type": "password", "placeholder": "Bearer token from app.biznet.id"},
            {"key": "api_token", "label": "API Token (Api-Token Header - Optional)", "type": "password", "placeholder": "Direct api-token (skips login-v2 if provided)"}
        ]

    def _build_headers(self, bearer_token: str = "", api_token: str = "") -> Dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "Origin": "https://app.biznet.id",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Referer": "https://app.biznet.id/",
            "Sec-Ch-Ua": '"Brave";v="155", "Chromium";v="155", "Not(A:Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Gpc": "1",
            "User-Agent": self.USER_AGENT
        }
        if bearer_token:
            auth_val = bearer_token.strip()
            if not auth_val.lower().startswith("bearer "):
                auth_val = f"Bearer {auth_val}"
            headers["Authorization"] = auth_val
        if api_token:
            headers["Api-token"] = api_token.strip()
        return headers

    def _get_api_token(self, username: str, password: str, bearer_token: str = "") -> str:
        if self._cached_token and time.time() < self._token_expires_at:
            return self._cached_token

        login_url = f"{self.API_BASE}/login-v2"
        payload = json.dumps({
            "username": username,
            "password": password,
            "rememberMe": True
        }).encode("utf-8")

        headers = self._build_headers(bearer_token=bearer_token)
        req = urllib.request.Request(login_url, data=payload, headers=headers)

        last_err = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)
                    token = (
                        data.get("api-token")
                        or data.get("data", {}).get("api-token")
                        or data.get("data", {}).get("token")
                        or data.get("token")
                    )
                    code = data.get("code")
                    if (str(code) == "200" or data.get("success") in (True, "true")) and token:
                        self._cached_token = str(token).strip()
                        self._token_expires_at = time.time() + 3600.0  # 1 hour TTL
                        return self._cached_token
                    else:
                        last_err = f"Biznet login-v2 failed: {data.get('message', 'Invalid credentials or response')}"
            except Exception as e:
                last_err = str(e)
                time.sleep(1.0)

        raise RuntimeError(last_err or "Failed to authenticate with MyBiznet API (login-v2) after 3 attempts.")

    def fetch_telemetry(self, credentials: Dict[str, Any]) -> BandwidthSnapshot:
        biznet_id = str(credentials.get("biznet_id", "")).strip()
        username = str(credentials.get("username", "")).strip()
        password = str(credentials.get("password", "")).strip()
        bearer_token = str(credentials.get("bearer_token", "")).strip()
        direct_api_token = str(credentials.get("api_token", "")).strip()

        if not biznet_id:
            return BandwidthSnapshot(
                provider_id=self.provider_id,
                provider_name=self.display_name,
                online=False,
                plan_speed_mbps=100.0,
                quota_remaining_bytes=0,
                quota_limit_bytes=0,
                reset_timestamp=0,
                last_downtime_reason="Unconfigured",
                last_downtime_sub="Contract number required",
                fetched_at=time.time(),
                error_message="Contract number not configured"
            )

        token = direct_api_token or self._cached_token
        if not token:
            if username and password:
                try:
                    token = self._get_api_token(username, password, bearer_token=bearer_token)
                except Exception as e:
                    return BandwidthSnapshot(
                        provider_id=self.provider_id,
                        provider_name=self.display_name,
                        online=False,
                        plan_speed_mbps=100.0,
                        quota_remaining_bytes=0,
                        quota_limit_bytes=0,
                        reset_timestamp=0,
                        last_downtime_reason="Auth Error",
                        last_downtime_sub=str(e),
                        fetched_at=time.time(),
                        error_message=str(e)
                    )
            else:
                return BandwidthSnapshot(
                    provider_id=self.provider_id,
                    provider_name=self.display_name,
                    online=False,
                    plan_speed_mbps=100.0,
                    quota_remaining_bytes=0,
                    quota_limit_bytes=0,
                    reset_timestamp=0,
                    last_downtime_reason="Unconfigured",
                    last_downtime_sub="Configure credentials or API Token in Settings",
                    fetched_at=time.time(),
                    error_message="Credentials incomplete"
                )

        headers = self._build_headers(bearer_token=bearer_token, api_token=token)

        quota_url = f"{self.API_BASE}/getQuotaV2?contractNumber={biznet_id}"
        bandwidth_url = f"{self.API_BASE}/getBandwidthV2?contractNumber={biznet_id}"
        modem_url = f"{self.API_BASE}/get-detail-modem-v2"

        try:
            # 1. Fetch Quota V2
            q_req = urllib.request.Request(quota_url, headers=headers)
            with urllib.request.urlopen(q_req, timeout=10.0) as q_resp:
                q_data = json.loads(q_resp.read().decode("utf-8"))

            # 2. Fetch Bandwidth V2
            b_req = urllib.request.Request(bandwidth_url, headers=headers)
            with urllib.request.urlopen(b_req, timeout=10.0) as b_resp:
                b_data = json.loads(b_resp.read().decode("utf-8"))

            # 3. Fetch Modem Detail V2 (Optional, non-fatal if fails)
            downtime_reason = "Dying-gasp"
            downtime_sub = "Power loss detected by OLT"
            try:
                m_payload = json.dumps({"contractNumber": biznet_id}).encode("utf-8")
                m_req = urllib.request.Request(modem_url, data=m_payload, headers=headers)
                with urllib.request.urlopen(m_req, timeout=10.0) as m_resp:
                    m_data = json.loads(m_resp.read().decode("utf-8"))
                    if isinstance(m_data, dict):
                        dt_val = (
                            m_data.get("lastDowntimeReason")
                            or m_data.get("last_downtime_reason")
                            or m_data.get("downtimeReason")
                            or m_data.get("data", {}).get("lastDowntimeReason")
                            or m_data.get("data", {}).get("downtimeReason")
                            or m_data.get("data", {}).get("status")
                        )
                        if dt_val:
                            downtime_reason = str(dt_val)
                        dt_sub = (
                            m_data.get("description")
                            or m_data.get("data", {}).get("description")
                            or m_data.get("data", {}).get("statusDescription")
                            or m_data.get("data", {}).get("message")
                        )
                        if dt_sub:
                            downtime_sub = str(dt_sub)
            except Exception:
                pass

            # Parse quota limits
            main_rem = float(q_data.get("mainKuota", {}).get("remainingLimit", 0))
            main_lim = float(q_data.get("mainKuota", {}).get("limit", 0))

            # Auto-detect bytes vs GB
            if main_lim < 10_000_000:
                main_rem_bytes = int(main_rem * (1024 ** 3))
                main_lim_bytes = int(main_lim * (1024 ** 3))
            else:
                main_rem_bytes = int(main_rem)
                main_lim_bytes = int(main_lim)

            # Parse valid until
            valid_str = (
                q_data.get("mainKuota", {}).get("mainKuota", {}).get("validUntil")
                or q_data.get("mainKuota", {}).get("validUntil")
                or ""
            )
            reset_ts = 0
            if valid_str:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y"):
                    try:
                        clean_str = valid_str.split(".")[0].strip()
                        reset_ts = int(datetime.strptime(clean_str, fmt).timestamp())
                        break
                    except Exception:
                        pass

            # Parse plan speed
            plan_speed = float(b_data.get("data", {}).get("active", {}).get("bandwidth", 100.0) or 100.0)

            return BandwidthSnapshot(
                provider_id=self.provider_id,
                provider_name=self.display_name,
                online=True,
                plan_speed_mbps=plan_speed,
                quota_remaining_bytes=main_rem_bytes,
                quota_limit_bytes=main_lim_bytes,
                reset_timestamp=reset_ts,
                last_downtime_reason=downtime_reason,
                last_downtime_sub=downtime_sub,
                fetched_at=time.time(),
                error_message=""
            )

        except urllib.error.HTTPError as he:
            if he.code in (401, 403):
                self._cached_token = None
                self._token_expires_at = 0.0
            return BandwidthSnapshot(
                provider_id=self.provider_id,
                provider_name=self.display_name,
                online=False,
                plan_speed_mbps=100.0,
                quota_remaining_bytes=0,
                quota_limit_bytes=0,
                reset_timestamp=0,
                last_downtime_reason="HTTP Error",
                last_downtime_sub=f"HTTP {he.code}: {he.reason}",
                fetched_at=time.time(),
                error_message=f"HTTP {he.code}: {he.reason}"
            )
        except Exception as e:
            return BandwidthSnapshot(
                provider_id=self.provider_id,
                provider_name=self.display_name,
                online=False,
                plan_speed_mbps=100.0,
                quota_remaining_bytes=0,
                quota_limit_bytes=0,
                reset_timestamp=0,
                last_downtime_reason="Connection Error",
                last_downtime_sub=str(e),
                fetched_at=time.time(),
                error_message=str(e)
            )
