from __future__ import annotations

import importlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .._cookies import load_cookies

USAGE_URL = "https://www.kimi.com/apiv2/kimi.gateway.billing.v1.BillingService/GetUsages"
COOKIE_DOMAIN = "kimi.com"
AUTH_COOKIE_NAME = "kimi-auth"
SCOPE_CODING = "FEATURE_CODING"


@dataclass
class KimiUsage:
    available: bool
    error: str | None = None
    primary_pct: float = 0.0
    primary_reset_at: int | None = None
    weekly_pct: float = 0.0
    weekly_reset_at: int | None = None


def _used_pct(detail: dict) -> float:
    if not isinstance(detail, dict):
        return 0.0
    try:
        limit = float(detail.get("limit", 0) or 0)
        remaining = float(detail.get("remaining", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    if limit <= 0:
        return 0.0
    used = max(limit - remaining, 0.0)
    return round(used / limit * 100.0, 2)


def _reset_epoch(detail: dict) -> int | None:
    if not isinstance(detail, dict):
        return None
    raw = detail.get("resetTime")
    if raw is None or raw == "":
        return None
    try:
        if isinstance(raw, (int, float)):
            epoch = float(raw)
            if epoch > 1e12:
                epoch = epoch / 1000.0
            return int(epoch)
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (TypeError, ValueError):
        return None


def _window_metrics(detail: dict, now_epoch: int) -> tuple[float, int | None]:
    # Kimi keeps returning the previous window (used%, past resetTime) until
    # the user makes a new request that lazily starts a fresh window. Auto-roll
    # expired windows to 0%/None so the statusbar matches Claude/OpenAI behavior.
    reset = _reset_epoch(detail)
    if reset is not None and reset <= now_epoch:
        return 0.0, None
    return _used_pct(detail), reset


def _five_hour_window(usage_obj: dict) -> dict | None:
    for w in usage_obj.get("limits") or []:
        window = (w or {}).get("window") or {}
        if window.get("timeUnit") == "TIME_UNIT_MINUTE" and int(window.get("duration", 0) or 0) == 300:
            return (w or {}).get("detail") or {}
    return None


def fetch_kimi(browser: str = "firefox") -> KimiUsage:
    try:
        requests = importlib.import_module("curl_cffi.requests")
    except ImportError:
        return KimiUsage(available=False, error="curl_cffi not installed")
    try:
        importlib.import_module("browser_cookie3")
    except ImportError:
        return KimiUsage(available=False, error="browser_cookie3 not installed")

    try:
        cj = load_cookies(browser, COOKIE_DOMAIN)
    except (FileNotFoundError, ValueError) as e:
        return KimiUsage(available=False, error=str(e))
    except Exception as e:
        return KimiUsage(available=False, error=f"cookie extraction failed: {e}")

    auth_value: str | None = None
    for c in cj:
        if c.name == AUTH_COOKIE_NAME:
            auth_value = c.value
            break
    if not auth_value:
        return KimiUsage(available=False, error=f"no {AUTH_COOKIE_NAME} cookie (logged out?)")

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/128.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_value}",
        "Referer": "https://www.kimi.com/code/console",
        "x-msh-platform": "web",
    }
    body = json.dumps({"scope": [SCOPE_CODING]})

    try:
        s = requests.Session(impersonate="firefox")
        r = s.post(USAGE_URL, headers=headers, cookies=cj, data=body, timeout=10)
        if r.status_code != 200:
            return KimiUsage(available=False, error=f"usage http {r.status_code}")
        data = r.json()
    except Exception as e:
        return KimiUsage(available=False, error=f"request failed: {e}")

    usage_obj = next(
        (u for u in (data.get("usages") or []) if (u or {}).get("scope") == SCOPE_CODING),
        None,
    )
    if usage_obj is None:
        return KimiUsage(available=False, error=f"no {SCOPE_CODING} usage in response")

    weekly_detail = usage_obj.get("detail") or {}
    five_hour_detail = _five_hour_window(usage_obj)
    if five_hour_detail is None:
        return KimiUsage(available=False, error="schema: no 5h window")
    now_epoch = int(time.time())
    primary_pct, primary_reset = _window_metrics(five_hour_detail, now_epoch)
    weekly_pct, weekly_reset = _window_metrics(weekly_detail, now_epoch)

    return KimiUsage(
        available=True,
        primary_pct=primary_pct,
        primary_reset_at=primary_reset,
        weekly_pct=weekly_pct,
        weekly_reset_at=weekly_reset,
    )
