"""Anthropic OAuth usage API client.

Fetches authoritative 5-hour and 7-day usage percentages directly from
Claude Code's internal endpoint. This is the same data Claude Code's
/status command displays.

Endpoint discovered in the Claude Code 2.1.83 binary:
    /api/oauth/usage

Auth: Bearer token from ~/.claude/.credentials.json
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
PROFILE_ENDPOINT = "https://api.anthropic.com/api/oauth/profile"
USER_AGENT = "claude-cli/2.1.83"
ANTHROPIC_BETA = "oauth-2025-04-20"


@dataclass
class ClaudeUsage:
    available: bool
    error: str | None = None
    five_hour_pct: float = 0.0
    five_hour_resets_at: datetime | None = None
    seven_day_pct: float = 0.0
    seven_day_resets_at: datetime | None = None
    seven_day_opus_pct: float | None = None
    seven_day_opus_resets_at: datetime | None = None
    seven_day_sonnet_pct: float | None = None
    seven_day_sonnet_resets_at: datetime | None = None
    subscription_type: str = "unknown"
    rate_limit_tier: str = "unknown"


def _read_token() -> tuple[str | None, str | None]:
    if not CREDENTIALS_FILE.exists():
        return None, f"credentials file not found: {CREDENTIALS_FILE}"
    try:
        data = json.loads(CREDENTIALS_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return None, f"failed to read credentials: {e}"
    oauth = data.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token:
        return None, "no accessToken in credentials"
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
    if err:
        return ClaudeUsage(available=False, error=err)
    if token is None:
        return ClaudeUsage(available=False, error="missing access token")

    profile, _ = _http_get(PROFILE_ENDPOINT, token)
    sub_type = "unknown"
    rl_tier = "unknown"
    if profile:
        org = profile.get("organization") or {}
        sub_type = org.get("organization_type") or "unknown"
        rl_tier = org.get("rate_limit_tier") or "unknown"

    data, err = _http_get(USAGE_ENDPOINT, token)
    if err or not data:
        return ClaudeUsage(
            available=False,
            error=err or "empty response",
            subscription_type=sub_type,
            rate_limit_tier=rl_tier,
        )

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
        subscription_type=sub_type,
        rate_limit_tier=rl_tier,
    )
