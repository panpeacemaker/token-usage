from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import aggregator, opencode_reader, reader
from .limits import PlanLimits
from .models import ClaudeUsage, UsageEntry


def _merge_sources(
    jsonl_root: Path | None,
    opencode_db: Path | None,
) -> list[UsageEntry]:
    entries: list[UsageEntry] = []
    entries.extend(reader.load_entries(jsonl_root))
    entries.extend(opencode_reader.load_entries(opencode_db))
    entries.sort(key=lambda e: e.timestamp)
    return entries


def _next_weekly_reset(
    now: datetime,
    weekday: int,
    hour_local: int,
) -> datetime | None:
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is None:
            return None
        now_local = now.astimezone(local_tz)
        days_ahead = (weekday - now_local.weekday()) % 7
        candidate = now_local.replace(
            hour=hour_local, minute=0, second=0, microsecond=0
        ) + timedelta(days=days_ahead)
        if candidate <= now_local:
            candidate += timedelta(days=7)
        return candidate.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def compute_local(
    plan_limits: PlanLimits,
    now: datetime | None = None,
    root: Path | None = None,
    opencode_db: Path | None = None,
    weekly_reset_weekday: int = 0,
    weekly_reset_hour_local: int = 22,
) -> tuple[ClaudeUsage, dict]:
    now = now or datetime.now(timezone.utc)

    try:
        entries = _merge_sources(root, opencode_db)
    except Exception as e:
        return (
            ClaudeUsage(available=False, error=f"local read failed: {e}"),
            {"error": str(e)},
        )

    summary = aggregator.summarize(entries, plan_limits, now=now)
    detail = {
        "active_block": summary.get("active_block"),
        "week": summary.get("week"),
        "total_entries": summary.get("total_entries"),
    }

    if not entries:
        return (
            ClaudeUsage(available=False, error="no local JSONL entries"),
            detail,
        )

    active = summary.get("active_block") or {}
    week = summary.get("week") or {}

    five_h_reset = None
    if active.get("present"):
        end_str = active.get("end_utc")
        if end_str:
            try:
                five_h_reset = datetime.fromisoformat(end_str)
            except (ValueError, TypeError):
                pass
    if five_h_reset is None:
        five_h_reset = now + timedelta(hours=5)

    seven_day_pct = float(week.get("pct") or 0)

    seven_d_reset = _next_weekly_reset(now, weekly_reset_weekday, weekly_reset_hour_local)

    usage = ClaudeUsage(
        available=True,
        five_hour_pct=float(active.get("pct") or 0),
        five_hour_resets_at=five_h_reset,
        seven_day_pct=seven_day_pct,
        seven_day_resets_at=seven_d_reset,
        subscription_type="local",
        rate_limit_tier=plan_limits.name,
    )
    return usage, detail
