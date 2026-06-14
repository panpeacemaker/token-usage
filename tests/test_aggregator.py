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


def test_cache_read_weight_default_counts_cache_read() -> None:
    from token_usage.claude.models import UsageEntry

    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        UsageEntry(now - timedelta(minutes=5), "m1", "r1", "sonnet", 100, 50, 20, 500000),
    ]
    limits = get_limits("pro", {"pro": {"tokens_5h": 1000000}})
    s = aggregator.summarize(entries, limits, now=now)
    assert s["active_block"]["effective_tokens"] == 500170
    assert s["active_block"]["pct"] == 50.0


def test_cache_read_weight_zero_ignores_cache_read() -> None:
    from token_usage.claude.models import UsageEntry

    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        UsageEntry(now - timedelta(minutes=5), "m1", "r1", "sonnet", 100, 50, 20, 500000),
    ]
    limits = get_limits("pro", {"pro": {"tokens_5h": 1000000}})
    s = aggregator.summarize(entries, limits, now=now, cache_read_weight=0.0)
    assert s["active_block"]["effective_tokens"] == 170
    assert s["active_block"]["pct"] == 0.0


def test_cache_read_weight_fractional() -> None:
    from token_usage.claude.models import UsageEntry

    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        UsageEntry(now - timedelta(minutes=5), "m1", "r1", "sonnet", 100, 50, 20, 1000),
    ]
    limits = get_limits("pro", {"pro": {"tokens_5h": 100000}})
    s = aggregator.summarize(entries, limits, now=now, cache_read_weight=0.5)
    assert s["active_block"]["effective_tokens"] == 670
    assert s["active_block"]["pct"] == 0.7


def test_anchored_weekly_start_excludes_older_entries() -> None:
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    anchor = now - timedelta(days=1)
    entries = [
        _entry(now - timedelta(minutes=5), 500),
        _entry(now - timedelta(days=2), 4000),
    ]
    limits = get_limits("pro")
    s = aggregator.summarize(entries, limits, now=now, weekly_start=anchor)
    assert s["week"]["tokens"] == 500
    assert s["week"]["start_utc"] == anchor.isoformat()


def test_weekly_start_none_falls_back_to_rolling_7d() -> None:
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        _entry(now - timedelta(days=1), 500),
        _entry(now - timedelta(days=10), 4000),
    ]
    limits = get_limits("pro")
    s = aggregator.summarize(entries, limits, now=now, weekly_start=None)
    assert s["week"]["tokens"] == 500
    assert s["week"]["start_utc"] == (now - timedelta(days=7)).isoformat()


def _turn(ts: datetime, mid: str, kind: str = "turn") -> UsageEntry:
    return UsageEntry(ts, mid, "req", "sonnet", 1000, 0, 0, 0, kind)


def test_weekly_messages_counts_only_real_turns() -> None:
    # A single user turn produces one real assistant turn plus several
    # tool-call / sidechain API records. Only real turns must be counted.
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        _turn(now - timedelta(minutes=5), "t1", "turn"),
        _turn(now - timedelta(minutes=4), "x1", "tool"),
        _turn(now - timedelta(minutes=3), "x2", "tool"),
        _turn(now - timedelta(minutes=2), "s1", "sidechain"),
        _turn(now - timedelta(minutes=1), "t2", "turn"),
    ]
    limits = get_limits("pro")
    s = aggregator.summarize(entries, limits, now=now)
    assert s["week"]["messages"] == 2


def test_pct_messages_never_exceeds_100_on_tool_overcount() -> None:
    # Heavy agentic usage: a few real turns but thousands of tool-call steps.
    # pct_messages must stay <= 100 because tool steps are not real messages.
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    limits = get_limits("pro")
    entries = [_turn(now - timedelta(minutes=1), f"tool{i}", "tool") for i in range(3000)]
    entries += [_turn(now - timedelta(minutes=2), f"turn{i}", "turn") for i in range(50)]
    s = aggregator.summarize(entries, limits, now=now)
    assert s["week"]["messages"] == 50
    assert s["week"]["pct_messages"] <= 100


def test_cache_read_weight_is_exposed_in_summary_dicts() -> None:
    from token_usage.claude.models import UsageEntry

    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        UsageEntry(now - timedelta(minutes=5), "m1", "r1", "sonnet", 100, 50, 20, 1000),
    ]
    limits = get_limits("pro", {"pro": {"tokens_5h": 100000, "tokens_weekly": 100000}})

    weight = 0.5
    s = aggregator.summarize(entries, limits, now=now, cache_read_weight=weight)

    assert s["active_block"]["cache_read_weight"] == weight
    assert s["week"]["cache_read_weight"] == weight

    for key in ("active_block", "week"):
        sub = s[key]
        assert sub["effective_tokens"] == int(
            sub["tokens"] + weight * sub["cache_read_tokens"]
        ), f"{key}: effective not reproducible from tokens + weight*cache_read"

    for key, limit_key in (("active_block", "limit_tokens"), ("week", "limit_tokens")):
        sub = s[key]
        expected_pct = round(sub["effective_tokens"] / sub[limit_key] * 100, 1)
        assert sub["pct"] == expected_pct, f"{key}: pct not reproducible"


def test_cache_read_weight_default_value_is_exposed() -> None:
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    limits = get_limits("pro", {"pro": {"tokens_5h": 100000, "tokens_weekly": 100000}})
    s = aggregator.summarize([], limits, now=now)
    assert s["active_block"]["cache_read_weight"] == 1.0
    assert s["week"]["cache_read_weight"] == 1.0


def test_cache_read_weight_zero_value_is_exposed() -> None:
    from token_usage.claude.models import UsageEntry

    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    entries = [
        UsageEntry(now - timedelta(minutes=5), "m1", "r1", "sonnet", 100, 50, 20, 1000),
    ]
    limits = get_limits("pro", {"pro": {"tokens_5h": 100000, "tokens_weekly": 100000}})
    s = aggregator.summarize(entries, limits, now=now, cache_read_weight=0.0)
    assert s["active_block"]["cache_read_weight"] == 0.0
    assert s["week"]["cache_read_weight"] == 0.0
    assert s["active_block"]["effective_tokens"] == s["active_block"]["tokens"]
