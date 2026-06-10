from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..cache import CACHE_DIR
from .models import ClaudeUsage

STATUSLINE_CACHE_FILE = CACHE_DIR / "statusline.json"
STATUSLINE_MAX_AGE_SECONDS = 600  # 10 min; stale file → fall through to OAuth


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


def window_validity(
    usage: ClaudeUsage | None,
    now: datetime | None = None,
    file_mtime: float | None = None,
    max_file_age_seconds: int = STATUSLINE_MAX_AGE_SECONDS,
) -> dict:
    """Return per-window and overall validity info.

    A window without a ``resets_at`` timestamp is treated as valid
    (preserving existing behaviour where missing data is not treated
    as expired).
    """
    result: dict = {
        "overall": False,
        "reason": None,
        "file_valid": False,
        "five_valid": False,
        "seven_valid": False,
    }
    if usage is None:
        result["reason"] = "file missing"
        return result
    if not usage.available:
        result["reason"] = f"unavailable: {usage.error}"
        return result
    now = now or datetime.now(timezone.utc)
    if file_mtime is not None:
        age = now.timestamp() - file_mtime
        if age < 0:
            result["reason"] = f"file mtime in future ({age:.0f}s)"
            return result
        if age > max_file_age_seconds:
            result["reason"] = f"file age {age:.0f}s > {max_file_age_seconds}s max"
            return result
    result["file_valid"] = True
    if usage.five_hour_resets_at is not None:
        result["five_valid"] = usage.five_hour_resets_at > now
    else:
        result["five_valid"] = True
    if usage.seven_day_resets_at is not None:
        result["seven_valid"] = usage.seven_day_resets_at > now
    else:
        result["seven_valid"] = True
    result["overall"] = result["five_valid"] or result["seven_valid"]
    if not result["overall"]:
        parts: list[str] = []
        if not result["five_valid"]:
            parts.append(
                f"5h window expired at {usage.five_hour_resets_at.isoformat()}"
                if usage.five_hour_resets_at
                else "5h window expired"
            )
        if not result["seven_valid"]:
            parts.append(
                f"7d window expired at {usage.seven_day_resets_at.isoformat()}"
                if usage.seven_day_resets_at
                else "7d window expired"
            )
        result["reason"] = "; ".join(parts)
    return result


def check_validity(
    usage: ClaudeUsage | None,
    now: datetime | None = None,
    file_mtime: float | None = None,
    max_file_age_seconds: int = STATUSLINE_MAX_AGE_SECONDS,
) -> tuple[bool, str | None]:
    result = window_validity(usage, now, file_mtime, max_file_age_seconds)
    return result["overall"], result["reason"]


def is_still_valid(
    usage: ClaudeUsage | None,
    now: datetime | None = None,
    file_mtime: float | None = None,
    max_file_age_seconds: int = STATUSLINE_MAX_AGE_SECONDS,
) -> bool:
    return window_validity(usage, now, file_mtime, max_file_age_seconds)["overall"]
