from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import aggregator, reader
from .limits import PlanLimits
from .models import ClaudeUsage


def compute_local(
    plan_limits: PlanLimits,
    now: datetime | None = None,
    root: Path | None = None,
) -> tuple[ClaudeUsage, dict]:
    now = now or datetime.now(timezone.utc)

    try:
        entries = reader.load_entries(root)
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

    seven_d_reset = None
    week_start_str = week.get("start_utc")
    if week_start_str:
        try:
            seven_d_reset = datetime.fromisoformat(week_start_str) + timedelta(days=7)
        except (ValueError, TypeError):
            pass

    week_pct_tokens = float(week.get("pct") or 0)
    week_pct_messages = float(week.get("pct_messages") or 0)
    seven_day_pct = max(week_pct_tokens, week_pct_messages)

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
