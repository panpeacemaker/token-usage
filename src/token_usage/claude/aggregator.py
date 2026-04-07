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


def week_start_utc(now: datetime | None = None, week_start_day: int = 0) -> datetime:
    now = now or datetime.now(timezone.utc)
    days_since_start = (now.weekday() - week_start_day) % 7
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_start)
    return start


def weekly_entries(entries: list[UsageEntry], now: datetime | None = None) -> list[UsageEntry]:
    start = week_start_utc(now)
    return [e for e in entries if e.timestamp >= start]


def summarize(entries: list[UsageEntry], limits: PlanLimits, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    blocks = compute_blocks(entries)
    active = active_block(blocks, now)
    wk = weekly_entries(entries, now)

    active_tokens = active.total_tokens if active else 0
    weekly_tokens = sum(e.total_tokens for e in wk)
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
            "limit_tokens": limits.tokens_5h,
            "pct": pct(active_tokens, limits.tokens_5h),
            "models": active.models if active else {},
        },
        "week": {
            "start_utc": week_start_utc(now).isoformat(),
            "tokens": weekly_tokens,
            "limit_tokens": limits.tokens_weekly,
            "pct": pct(weekly_tokens, limits.tokens_weekly),
            "messages": weekly_messages,
            "limit_messages": limits.messages_weekly,
            "pct_messages": pct(weekly_messages, limits.messages_weekly),
        },
        "total_blocks": len([b for b in blocks if not b.is_gap]),
        "total_entries": len(entries),
    }
