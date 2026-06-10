from __future__ import annotations

from datetime import datetime, timedelta, timezone

from token_usage.claude import aggregator
from token_usage.claude.limits import get_limits
from token_usage.claude.models import UsageEntry


def _entry(ts: datetime, tokens: int = 1000) -> UsageEntry:
    return UsageEntry(ts, f"msg{ts.timestamp()}", "req", "claude-sonnet-4-6", tokens, 0, 0, 0)


def test_active_block_detected() -> None:
    now = datetime(2026, 4, 5, 12, 30, tzinfo=timezone.utc)
    entries = [_entry(now - timedelta(minutes=30), 500), _entry(now - timedelta(minutes=15), 500)]
    limits = get_limits("pro")
    s = aggregator.summarize(entries, limits, now=now)
    assert s["active_block"]["present"] is True
    assert s["active_block"]["tokens"] == 1000


def test_week_totals() -> None:
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [_entry(now - timedelta(days=1), 2000), _entry(now - timedelta(days=10), 5000)]
    limits = get_limits("pro")
    s = aggregator.summarize(entries, limits, now=now)
    assert s["week"]["tokens"] == 2000


def test_week_totals_exclude_cache_read() -> None:
    from token_usage.claude.models import UsageEntry

    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        UsageEntry(now - timedelta(days=1), "m1", "r1", "sonnet", 1000, 500, 200, 999999),
    ]
    limits = get_limits("pro")
    s = aggregator.summarize(entries, limits, now=now)
    assert s["week"]["tokens"] == 1700
    assert s["week"]["cache_read_tokens"] == 999999


def test_active_block_excludes_cache_read() -> None:
    from token_usage.claude.models import UsageEntry

    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        UsageEntry(now - timedelta(minutes=5), "m1", "r1", "sonnet", 100, 50, 20, 500000),
    ]
    limits = get_limits("pro")
    s = aggregator.summarize(entries, limits, now=now)
    assert s["active_block"]["tokens"] == 170
    assert s["active_block"]["cache_read_tokens"] == 500000
