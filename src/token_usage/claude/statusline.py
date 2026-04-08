from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..cache import CACHE_DIR
from .models import ClaudeUsage

STATUSLINE_CACHE_FILE = CACHE_DIR / "statusline.json"


def _epoch_to_dt(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def read_statusline_usage(path: Path | None = None) -> ClaudeUsage | None:
    path = path or STATUSLINE_CACHE_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    rate_limits = data.get("rate_limits") or {}
    five_hour = rate_limits.get("five_hour") or {}
    seven_day = rate_limits.get("seven_day") or {}

    five_pct = five_hour.get("used_percentage")
    seven_pct = seven_day.get("used_percentage")

    if five_pct is None and seven_pct is None:
        return ClaudeUsage(
            available=False,
            error="statusline cache has no rate_limits (API user, first message, or anonymous)",
        )

    return ClaudeUsage(
        available=True,
        five_hour_pct=float(five_pct) if five_pct is not None else 0.0,
        five_hour_resets_at=_epoch_to_dt(five_hour.get("resets_at")),
        seven_day_pct=float(seven_pct) if seven_pct is not None else 0.0,
        seven_day_resets_at=_epoch_to_dt(seven_day.get("resets_at")),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )


def is_still_valid(usage: ClaudeUsage | None, now: datetime | None = None) -> bool:
    if usage is None or not usage.available:
        return False
    now = now or datetime.now(timezone.utc)
    if usage.five_hour_resets_at and usage.five_hour_resets_at > now:
        return True
    if usage.seven_day_resets_at and usage.seven_day_resets_at > now:
        return True
    return False
