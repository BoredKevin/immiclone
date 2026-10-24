import os
import json
import time
import urllib.request
import urllib.parse
from dashboard.config import TAILSCALE_CONF_PATH, STATE_LOCK, atomic_write_json

def load_tailscale_config():
    """Loads Tailscale configuration from disk."""
    with STATE_LOCK:
        if os.path.exists(TAILSCALE_CONF_PATH):
            try:
                with open(TAILSCALE_CONF_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Error loading Tailscale config: {e}")
        return {
            "mode": "auth_key", # "auth_key", "api", or "oauth"
            "auth_key": "",
            "api_key": "",
            "oauth_client_id": "",
            "oauth_client_secret": "",
            "tailnet": "",
            "auto_inject": True,
            "ephemeral": True,
            "tags": ["tag:worker"],
            "last_updated": 0
        }

def save_tailscale_config(cfg):
    """Saves Tailscale configuration atomically."""
    with STATE_LOCK:
        cfg["last_updated"] = int(time.time())
        return atomic_write_json(TAILSCALE_CONF_PATH, cfg)

def mask_secret(s):
    """Masks credentials for safe API responses."""
    if not s:
        return ""
    if len(s) <= 8:
        return "••••••••"
    return f"{s[:6]}••••••••{s[-4:]}"

def get_effective_tailscale_key():
    """Returns an active auth key: stored static key, or freshly generated via Tailscale API."""
    cfg = load_tailscale_config()
    mode = cfg.get("mode", "auth_key")
    auth_key = cfg.get("auth_key", "").strip()

    if mode == "auth_key" and auth_key:
        return auth_key

    api_key = cfg.get("api_key", "").strip()
    client_id = cfg.get("oauth_client_id", "").strip()
    client_secret = cfg.get("oauth_client_secret", "").strip()
    tailnet = cfg.get("tailnet", "").strip() or "-"

    bearer_token = ""
    if client_id and client_secret:
        # OAuth token exchange
        try:
            data = urllib.parse.urlencode({
                "client_id": client_id,
                "client_secret": client_secret
            }).encode()
            req = urllib.request.Request("https://api.tailscale.com/api/v2/oauth/token", data=data, method="POST")
            with urllib.request.urlopen(req, timeout=8) as resp:
                res = json.loads(resp.read().decode())
                bearer_token = res.get("access_token", "")
        except Exception as e:
            print(f"[!] OAuth token error: {e}")
            return auth_key
    elif api_key:
        bearer_token = api_key

    if bearer_token:
        try:
            url = f"https://api.tailscale.com/api/v2/tailnet/{tailnet}/keys"
            body = {
                "capabilities": {
                    "devices": {
                        "create": {
                            "reusable": False,
                            "ephemeral": cfg.get("ephemeral", True),
                            "preauthorized": True,
                            "tags": cfg.get("tags", ["tag:worker"])
                        }
                    }
                },
                "expirySeconds": 3600
            }
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"},
                data=json.dumps(body).encode(),
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                res = json.loads(resp.read().decode())
                return res.get("key", auth_key)
        except Exception as e:
            print(f"[!] Generate key error: {e}")

    return auth_key

def test_tailscale_connection():
    """Validates the current configured Tailscale credentials."""
    key = get_effective_tailscale_key()
    if key and key.startswith("tskey-"):
        return {"status": "SUCCESS", "message": f"Valid Tailscale key active ({mask_secret(key)})"}
    elif key:
        return {"status": "SUCCESS", "message": f"Key present: {mask_secret(key)}"}
    else:
        return {"status": "EMPTY", "message": "No active Tailscale key configured."}
