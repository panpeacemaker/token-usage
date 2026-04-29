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


def test_kimi_section_rendered_when_provided():
    kimi = {
        "available": True,
        "primary_pct": 18.0,
        "weekly_pct": 10.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
    }
    out = format_detail(_base_summary(), None, kimi)
    assert "Kimi Code" in out
    assert "5-hour:" in out
    assert "18.0%" in out
    assert "weekly:" in out
    assert "10.0%" in out


def test_kimi_unavailable():
    kimi = {"available": False, "error": "logged out"}
    out = format_detail(_base_summary(), None, kimi)
    assert "Kimi Code" in out
    assert "logged out" in out


def test_only_kimi_skips_claude_and_chatgpt_sections():
    kimi = {
        "available": True,
        "primary_pct": 25.0,
        "weekly_pct": 12.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
    }
    out = format_detail(None, None, kimi)
    assert "Claude" not in out
    assert "ChatGPT" not in out
    assert "Kimi Code" in out
    assert "25.0%" in out


def test_only_claude_skips_chatgpt_and_kimi_sections():
    out = format_detail(_base_summary(), None, None)
    assert "Claude" in out
    assert "ChatGPT" not in out
    assert "Kimi Code" not in out


def test_only_chatgpt_skips_claude_and_kimi_sections():
    openai = {"available": True, "primary_pct": 30.0, "review_pct": 5.0}
    out = format_detail(None, openai, None)
    assert "Claude" not in out
    assert "ChatGPT Plus" in out
    assert "Kimi Code" not in out
    assert "30.0%" in out


def test_empty_summary_dict_skips_claude_section():
    out = format_detail({}, {"available": False, "error": "x"}, None)
    assert "Claude" not in out
    assert "ChatGPT Plus" in out


def test_no_args_returns_empty_string():
    assert format_detail() == ""
    assert format_detail(None, None, None) == ""


def test_sections_separated_by_blank_line():
    openai = {"available": True, "primary_pct": 30.0, "review_pct": 5.0}
    kimi = {"available": True, "primary_pct": 18.0, "weekly_pct": 10.0}
    out = format_detail(_base_summary(), openai, kimi)
    assert "\n\n" in out
    parts = out.split("\n\n")
    assert any("Claude" in p for p in parts)
    assert any("ChatGPT" in p for p in parts)
    assert any("Kimi" in p for p in parts)


def test_opencode_section_rendered_when_provided():
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "primary_pct": 18.0,
        "weekly_pct": 12.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
        "primary_tokens": 18000,
        "primary_limit_tokens": 100000,
        "weekly_tokens": 60000,
        "weekly_limit_tokens": 500000,
    }
    out = format_detail(_base_summary(), None, None, opencode)
    assert "OpenCode" in out
    assert "18.0%" in out
    assert "12.0%" in out
    assert "18,000" in out
    assert "60,000" in out


def test_opencode_unavailable():
    opencode = {"available": False, "error": "no db"}
    out = format_detail(_base_summary(), None, None, opencode)
    assert "OpenCode" in out
    assert "no db" in out


def test_only_opencode_skips_other_sections():
    opencode = {"available": True, "provider_id": "opencode", "primary_pct": 25.0, "weekly_pct": 5.0}
    out = format_detail(None, None, None, opencode)
    assert "Claude" not in out
    assert "ChatGPT" not in out
    assert "Kimi Code" not in out
    assert "OpenCode" in out


def test_opencode_go_section_rendered_when_provided():
    opencode_go = {
        "available": True,
        "provider_id": "opencode-go",
        "primary_pct": 25.0,
        "weekly_pct": 8.0,
    }
    out = format_detail(None, None, None, None, opencode_go)
    assert "OpenCode Go" in out
    assert "opencode-go" in out
    assert "25.0%" in out


def test_opencode_and_go_both_rendered_in_detail():
    opencode = {"available": True, "provider_id": "opencode", "primary_pct": 5.0, "weekly_pct": 1.0}
    opencode_go = {"available": True, "provider_id": "opencode-go", "primary_pct": 25.0, "weekly_pct": 8.0}
    out = format_detail(None, None, None, opencode, opencode_go)
    assert "OpenCode (opencode)" in out
    assert "OpenCode Go (opencode-go)" in out
