import time
import json
import urllib.request
import urllib.error
from dashboard.config import (
    APP_VERSION,
    STATE_LOCK,
    get_version_metadata,
    get_git_info
)

GITHUB_REPO = "BoredKevin/immiclone"
GITHUB_COMMITS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
GITHUB_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CACHE_TTL = 900  # 15 minutes cache window

_update_cache = {
    "last_checked": 0,
    "data": None
}

def get_update_status():
    """Returns the latest update status, initiating a cached check if never run."""
    with STATE_LOCK:
        if _update_cache["data"] is not None and (time.time() - _update_cache["last_checked"] < CACHE_TTL):
            return _update_cache["data"]
    return check_for_updates(force=False)

def check_for_updates(force=False):
    """Checks upstream GitHub repository for new commits or releases."""
    global _update_cache
    now = time.time()

    with STATE_LOCK:
        if not force and _update_cache["data"] is not None and (now - _update_cache["last_checked"] < CACHE_TTL):
            return _update_cache["data"]

    ver_meta = get_version_metadata()
    local_commit = ver_meta["git"]["commit"]
    local_short = ver_meta["git"]["commit_short"]

    result = {
        "status": "up_to_date",
        "update_available": False,
        "current_version": APP_VERSION,
        "current_commit": local_short,
        "latest_version": APP_VERSION,
        "latest_commit": local_short,
        "behind_by": 0,
        "latest_commit_details": None,
        "last_checked": int(now),
        "github_repo_url": f"https://github.com/{GITHUB_REPO}",
        "message": "System is running the latest version."
    }

    req = urllib.request.Request(
        GITHUB_COMMITS_URL,
        headers={
            "User-Agent": f"Immiclone-UpdateChecker/{APP_VERSION}",
            "Accept": "application/vnd.github.v3+json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            remote_sha = data.get("sha", "")
            remote_short = remote_sha[:7] if remote_sha else "unknown"

            commit_info = data.get("commit", {})
            author_info = commit_info.get("author", {})
            message = commit_info.get("message", "").split("\n")[0]
            date_str = author_info.get("date", "")
            author_name = author_info.get("name", "Unknown")

            if remote_sha and local_commit != "unknown" and not local_commit.startswith(remote_sha) and not remote_sha.startswith(local_commit):
                result["status"] = "update_available"
                result["update_available"] = True
                result["latest_commit"] = remote_short
                result["behind_by"] = 1
                result["message"] = f"Update available: {remote_short} ({message})"
                result["latest_commit_details"] = {
                    "sha": remote_sha,
                    "sha_short": remote_short,
                    "message": message,
                    "author": author_name,
                    "date": date_str,
                    "html_url": data.get("html_url", f"https://github.com/{GITHUB_REPO}/commit/{remote_sha}")
                }
            else:
                result["status"] = "up_to_date"
                result["update_available"] = False
                result["latest_commit"] = local_short
                result["message"] = f"Up to date with main ({local_short})."

    except urllib.error.HTTPError as err:
        if err.code == 409:
            # 409 Conflict: Git Repository is empty on GitHub (no commits pushed yet)
            result["status"] = "up_to_date"
            result["update_available"] = False
            result["message"] = "Remote repository has no new commits."
        elif err.code == 403:
            # Rate limited
            result["status"] = "rate_limited"
            result["message"] = "GitHub API rate limit exceeded. Try again later."
        elif err.code == 404:
            result["status"] = "not_found"
            result["message"] = "Remote repository not found or private."
        else:
            result["status"] = "error"
            result["message"] = f"GitHub API returned HTTP {err.code}."
    except Exception as e:
        result["status"] = "offline"
        result["message"] = f"Could not check for updates: {e}"

    with STATE_LOCK:
        _update_cache["last_checked"] = now
        _update_cache["data"] = result

    return result
