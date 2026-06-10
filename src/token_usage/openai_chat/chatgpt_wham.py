from __future__ import annotations

import importlib
from dataclasses import dataclass

from .._cookies import load_cookies

WHAM_URL = "https://chatgpt.com/backend-api/wham/usage"
SESSION_URL = "https://chatgpt.com/api/auth/session"
COOKIE_DOMAIN = "chatgpt.com"


@dataclass
class ChatGPTUsage:
    available: bool
    error: str | None = None
    primary_pct: float = 0.0
    primary_reset_at: int | None = None
    weekly_pct: float = 0.0
    weekly_reset_at: int | None = None
    review_pct: float = 0.0
    review_reset_at: int | None = None


def _pct(obj) -> float:
    v = obj.get("used_percent") if isinstance(obj, dict) else None
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _reset(obj) -> int | None:
    v = obj.get("reset_at") if isinstance(obj, dict) else None
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def fetch_chatgpt(browser: str = "firefox") -> ChatGPTUsage:
    try:
        requests = importlib.import_module("curl_cffi.requests")
    except ImportError:
        return ChatGPTUsage(available=False, error="curl_cffi not installed")
    try:
        importlib.import_module("browser_cookie3")
    except ImportError:
        return ChatGPTUsage(available=False, error="browser_cookie3 not installed")

    try:
        cj = load_cookies(browser, COOKIE_DOMAIN)
    except (FileNotFoundError, ValueError) as e:
        return ChatGPTUsage(available=False, error=str(e))
    except Exception as e:
        return ChatGPTUsage(available=False, error=f"cookie extraction failed: {e}")

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/128.0",
        "Accept": "application/json",
    }

    try:
        s = requests.Session(impersonate="firefox")
        r = s.get(SESSION_URL, headers=headers, cookies=cj, timeout=10)
        if r.status_code != 200:
            return ChatGPTUsage(available=False, error=f"session http {r.status_code}")
        session_data = r.json()
        token = session_data.get("accessToken")
        if not token:
            return ChatGPTUsage(available=False, error="no access token (logged out?)")

        headers2 = {**headers, "Authorization": f"Bearer {token}"}
        r2 = s.get(WHAM_URL, headers=headers2, cookies=cj, timeout=10)
        if r2.status_code != 200:
            return ChatGPTUsage(available=False, error=f"wham http {r2.status_code}")
        data = r2.json()
    except Exception as e:
        return ChatGPTUsage(available=False, error=f"request failed: {e}")

    rl = data.get("rate_limit") or {}
    primary = rl.get("primary_window") or {}
    if not isinstance(primary, dict) or "used_percent" not in primary:
        return ChatGPTUsage(available=False, error="schema: missing primary_window used_percent")
    secondary = rl.get("secondary_window") or {}
    code = data.get("code_review_rate_limit") or {}

    return ChatGPTUsage(
        available=True,
        primary_pct=_pct(primary),
        primary_reset_at=_reset(primary),
        weekly_pct=_pct(secondary),
        weekly_reset_at=_reset(secondary),
        review_pct=_pct(code),
        review_reset_at=_reset(code),
    )
