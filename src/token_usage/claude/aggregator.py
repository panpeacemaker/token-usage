from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .blocks import compute_blocks
from .limits import PlanLimits
from .models import SessionBlock, UsageEntry


def active_block(blocks: list[SessionBlock], now: datetime | None = None) -> SessionBlock | None:
    now = now or datetime.now(timezone.utc)
    for b in blocks:
        if b.is_gap:
            continue
        if b.contains(now):
            return b
    return None


def seven_day_start_utc(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=7)


def weekly_entries(entries: list[UsageEntry], now: datetime | None = None) -> list[UsageEntry]:
    start = seven_day_start_utc(now)
    return [e for e in entries if e.timestamp >= start]


def summarize(
    entries: list[UsageEntry],
    limits: PlanLimits,
    now: datetime | None = None,
    cache_read_weight: float = 1.0,
) -> dict:
    now = now or datetime.now(timezone.utc)
    blocks = compute_blocks(entries)
    active = active_block(blocks, now)
    wk = weekly_entries(entries, now)

    active_tokens = active.billed_tokens if active else 0
    active_cache_read = sum(e.cache_read_tokens for e in active.entries) if active else 0
    active_effective = int(active_tokens + cache_read_weight * active_cache_read)
    weekly_tokens = sum(e.billed_tokens for e in wk)
    weekly_cache_read = sum(e.cache_read_tokens for e in wk)
    weekly_effective = int(weekly_tokens + cache_read_weight * weekly_cache_read)
    weekly_messages = len({e.message_id for e in wk if e.message_id})

    def pct(used: int, limit: int) -> float:
        return round(used / limit * 100, 1) if limit > 0 else 0.0

    return {
        "plan": limits.name,
        "now_utc": now.isoformat(),
        "active_block": {
            "present": active is not None,
            "start_utc": active.start.isoformat() if active else None,
            "end_utc": active.end.isoformat() if active else None,
            "tokens": active_tokens,
            "cache_read_tokens": active_cache_read,
            "effective_tokens": active_effective,
            "limit_tokens": limits.tokens_5h,
            "pct": pct(active_effective, limits.tokens_5h),
            "models": active.models if active else {},
        },
        "week": {
            "start_utc": seven_day_start_utc(now).isoformat(),
            "tokens": weekly_tokens,
            "cache_read_tokens": weekly_cache_read,
            "effective_tokens": weekly_effective,
            "limit_tokens": limits.tokens_weekly,
            "pct": pct(weekly_effective, limits.tokens_weekly),
            "messages": weekly_messages,
            "limit_messages": limits.messages_weekly,
            "pct_messages": pct(weekly_messages, limits.messages_weekly),
        },
        "total_blocks": len([b for b in blocks if not b.is_gap]),
        "total_entries": len(entries),
    }
