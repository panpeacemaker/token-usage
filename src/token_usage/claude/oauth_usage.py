from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .models import ClaudeUsage

CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
OPENCODE_AUTH_FILE = Path.home() / ".local" / "share" / "opencode" / "auth.json"
USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
USER_AGENT = "claude-cli/2.1.83"
ANTHROPIC_BETA = "oauth-2025-04-20"


def _read_token() -> tuple[str | None, str | None]:
    for candidate in _token_candidates():
        token, err = candidate()
        if token:
            return token, None
        if err and "not found" not in err:
            return None, err
    return None, "no OAuth token in ~/.claude/.credentials.json or ~/.local/share/opencode/auth.json"


def _token_candidates():
    return [_read_claude_credentials, _read_opencode_credentials]


def _read_claude_credentials() -> tuple[str | None, str | None]:
    if not CREDENTIALS_FILE.exists():
        return None, f"{CREDENTIALS_FILE} not found"
    try:
        data = json.loads(CREDENTIALS_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return None, f"failed to read {CREDENTIALS_FILE}: {e}"
    oauth = data.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token:
        return None, f"no accessToken in {CREDENTIALS_FILE}"
    return token, None


def _read_opencode_credentials() -> tuple[str | None, str | None]:
    if not OPENCODE_AUTH_FILE.exists():
        return None, f"{OPENCODE_AUTH_FILE} not found"
    try:
        data = json.loads(OPENCODE_AUTH_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return None, f"failed to read {OPENCODE_AUTH_FILE}: {e}"
    anthropic = data.get("anthropic") or {}
    if anthropic.get("type") != "oauth":
        return None, f"{OPENCODE_AUTH_FILE} anthropic section is not oauth"
    token = anthropic.get("access")
    if not token:
        return None, f"no access token in {OPENCODE_AUTH_FILE}"
    return token, None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _http_get(url: str, token: str, timeout: int = 10) -> tuple[dict | None, str | None]:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("anthropic-beta", ANTHROPIC_BETA)
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body), None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        return None, f"http {e.code}: {body}"
    except urllib.error.URLError as e:
        return None, f"url error: {e.reason}"
    except (OSError, json.JSONDecodeError) as e:
        return None, f"read/parse error: {e}"


def fetch_usage() -> ClaudeUsage:
    token, err = _read_token()
    if err or token is None:
        return ClaudeUsage(available=False, error=err or "missing oauth token")

    data, err = _http_get(USAGE_ENDPOINT, token)
    if err or not data:
        return ClaudeUsage(available=False, error=err or "empty response")

    def _pct(obj) -> float:
        if not isinstance(obj, dict):
            return 0.0
        v = obj.get("utilization")
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _reset(obj) -> datetime | None:
        if not isinstance(obj, dict):
            return None
        return _parse_iso(obj.get("resets_at"))

    five = data.get("five_hour") or {}
    seven = data.get("seven_day") or {}
    seven_opus = data.get("seven_day_opus")
    seven_sonnet = data.get("seven_day_sonnet")

    return ClaudeUsage(
        available=True,
        five_hour_pct=_pct(five),
        five_hour_resets_at=_reset(five),
        seven_day_pct=_pct(seven),
        seven_day_resets_at=_reset(seven),
        seven_day_opus_pct=_pct(seven_opus) if seven_opus else None,
        seven_day_opus_resets_at=_reset(seven_opus) if seven_opus else None,
        seven_day_sonnet_pct=_pct(seven_sonnet) if seven_sonnet else None,
        seven_day_sonnet_resets_at=_reset(seven_sonnet) if seven_sonnet else None,
        subscription_type="claude-max",
        rate_limit_tier="oauth",
    )
