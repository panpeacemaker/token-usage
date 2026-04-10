from __future__ import annotations

import time

from token_usage.formatters.detail import format_detail


def _base_summary(**overrides) -> dict:
    base = {
        "available": True,
        "five_hour_pct": 42.0,
        "five_hour_resets_at": "2026-04-10T14:00:00+00:00",
        "seven_day_pct": 15.0,
        "seven_day_resets_at": "2026-04-15T22:00:00+00:00",
        "subscription_type": "claude-code",
        "rate_limit_tier": "max5",
        "_source": "statusline",
        "local": {"total_entries": 0},
    }
    base.update(overrides)
    return base


def test_basic_output():
    out = format_detail(_base_summary())
    assert "Claude" in out
    assert "42.0%" in out
    assert "15.0%" in out


def test_stale_marker():
    s = _base_summary(
        _stale=True,
        _stale_reason="oauth failed (http 429); no local data; using expired statusline",
        _fetched_at=time.time() - 120,
    )
    out = format_detail(s)
    assert "[STALE]" in out
    assert "oauth failed" in out
    assert "cached data" in out


def test_stale_without_fetched_at():
    s = _base_summary(_stale=True, _stale_reason="unknown")
    out = format_detail(s)
    assert "[STALE]" in out
    assert "showing cached data" in out


def test_opus_and_sonnet_pct():
    s = _base_summary(seven_day_opus_pct=8.5, seven_day_sonnet_pct=6.5)
    out = format_detail(s)
    assert "opus" in out
    assert "8.5%" in out
    assert "sonnet" in out
    assert "6.5%" in out


def test_unavailable():
    s = _base_summary(available=False, error="no source")
    out = format_detail(s)
    assert "unavailable" in out
    assert "no source" in out


def test_local_block_stats():
    s = _base_summary(
        local={
            "active_block": {"present": True, "tokens": 50000, "models": {"claude-sonnet-4-6": 50000}},
            "week": {"messages": 10, "tokens": 100000},
            "total_entries": 42,
        }
    )
    out = format_detail(s)
    assert "50,000" in out
    assert "Local JSONL" in out


def test_openai_section():
    openai = {"available": True, "primary_pct": 30.0, "review_pct": 5.0}
    out = format_detail(_base_summary(), openai)
    assert "ChatGPT Plus" in out
    assert "30.0%" in out


def test_openai_unavailable():
    openai = {"available": False, "error": "cookie extraction failed"}
    out = format_detail(_base_summary(), openai)
    assert "cookie extraction failed" in out
