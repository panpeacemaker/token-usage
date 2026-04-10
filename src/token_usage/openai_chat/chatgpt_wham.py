from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

WHAM_URL = "https://chatgpt.com/backend-api/wham/usage"
SESSION_URL = "https://chatgpt.com/api/auth/session"


@dataclass
class ChatGPTUsage:
    available: bool
    error: str | None = None
    primary_pct: float = 0.0
    primary_reset_at: int | None = None
    review_pct: float = 0.0
    review_reset_at: int | None = None


def _zen_cookie_file() -> Path | None:
    """Find the cookies.sqlite in ~/.zen/<profile>/ — prefer 'Default' profiles."""
    zen_root = Path.home() / ".zen"
    if not zen_root.exists():
        return None
    candidates = sorted(
        zen_root.glob("*/cookies.sqlite"),
        key=lambda p: (0 if "Default" in p.parent.name else 1, p.parent.name),
    )
    return candidates[0] if candidates else None


def fetch_chatgpt(browser: str = "firefox") -> ChatGPTUsage:
    try:
        requests = importlib.import_module("curl_cffi.requests")
    except ImportError:
        return ChatGPTUsage(available=False, error="curl_cffi not installed")
    try:
        browser_cookie3 = importlib.import_module("browser_cookie3")
    except ImportError:
        return ChatGPTUsage(available=False, error="browser_cookie3 not installed")

    try:
        browser_lower = browser.lower()
        if browser_lower == "zen":
            zen_file = _zen_cookie_file()
            if zen_file is None:
                return ChatGPTUsage(available=False, error="Zen profile not found")
            cj = browser_cookie3.firefox(cookie_file=str(zen_file), domain_name="chatgpt.com")
        else:
            cj_func = {
                "firefox": browser_cookie3.firefox,
                "chrome": browser_cookie3.chrome,
                "chromium": browser_cookie3.chromium,
                "brave": browser_cookie3.brave,
            }.get(browser_lower, browser_cookie3.firefox)
            cj = cj_func(domain_name="chatgpt.com")
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
    code = data.get("code_review_rate_limit") or {}

    def pct(obj) -> float:
        v = obj.get("used_percent") if isinstance(obj, dict) else None
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def reset(obj) -> int | None:
        v = obj.get("reset_at") if isinstance(obj, dict) else None
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return ChatGPTUsage(
        available=True,
        primary_pct=pct(primary),
        primary_reset_at=reset(primary),
        review_pct=pct(code),
        review_reset_at=reset(code),
    )
