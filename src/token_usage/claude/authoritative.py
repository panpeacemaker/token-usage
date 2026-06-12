from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from ..cache import CACHE_DIR
from .models import ClaudeUsage

LKG_FILE = CACHE_DIR / "claude_lkg.json"


def _dt_to_epoch(value: datetime | None) -> float | None:
    if value is None:
        return None
    return value.timestamp()


def _epoch_to_dt(value: float | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def save(usage: ClaudeUsage, source: str) -> None:
    payload = {
        "saved_at": time.time(),
        "source": source,
        "subscription_type": usage.subscription_type,
        "rate_limit_tier": usage.rate_limit_tier,
        "five_hour_pct": usage.five_hour_pct,
        "five_hour_resets_at": _dt_to_epoch(usage.five_hour_resets_at),
        "seven_day_pct": usage.seven_day_pct,
        "seven_day_resets_at": _dt_to_epoch(usage.seven_day_resets_at),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LKG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, default=str))
    tmp.replace(LKG_FILE)


def load() -> tuple[ClaudeUsage, str, float] | None:
    if not LKG_FILE.exists():
        return None
    try:
        data = json.loads(LKG_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    required = ("saved_at", "source", "five_hour_pct", "seven_day_pct")
    if not all(k in data for k in required):
        return None

    saved_at = data["saved_at"]
    if not isinstance(saved_at, (int, float)):
        return None

    five_reset = _epoch_to_dt(data.get("five_hour_resets_at"))
    seven_reset = _epoch_to_dt(data.get("seven_day_resets_at"))

    try:
        usage = ClaudeUsage(
            available=True,
            five_hour_pct=float(data["five_hour_pct"]),
            five_hour_resets_at=five_reset,
            seven_day_pct=float(data["seven_day_pct"]),
            seven_day_resets_at=seven_reset,
            subscription_type=str(data.get("subscription_type", "unknown")),
            rate_limit_tier=str(data.get("rate_limit_tier", "unknown")),
        )
    except (TypeError, ValueError):
        return None
    return usage, str(data["source"]), float(saved_at)
