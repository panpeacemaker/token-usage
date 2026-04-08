from __future__ import annotations

import importlib
import time
from unittest.mock import patch

from token_usage.claude.oauth_usage import ClaudeUsage

cli_mod = importlib.import_module("token_usage.cli")
cache_mod = importlib.import_module("token_usage.cache")
config_mod = importlib.import_module("token_usage.config")


GOOD_SUMMARY = {
    "available": True,
    "error": None,
    "five_hour_pct": 42.0,
    "five_hour_resets_at": "2026-04-08T02:00:00+00:00",
    "seven_day_pct": 15.0,
    "seven_day_resets_at": "2026-04-13T20:00:00+00:00",
    "subscription_type": "claude_max",
    "rate_limit_tier": "default_claude_max_5x",
}


def _cfg(**overrides):
    cfg = config_mod.Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_uses_fresh_cache_when_available() -> None:
    cfg = _cfg(cache_ttl_seconds=300, openai_enabled=False)
    fresh = {
        **GOOD_SUMMARY,
        "fetched_at": time.time(),
        "next_retry_at": 0,
        "_version": cache_mod.CACHE_VERSION,
    }
    with patch.object(cache_mod, "read", return_value={"summary": GOOD_SUMMARY, "openai": None}), \
         patch.object(cache_mod, "read_raw", return_value=fresh), \
         patch.object(cli_mod, "fetch_claude_usage") as mock_fetch:
        summary, openai = cli_mod._build_summary(cfg)

    assert summary == GOOD_SUMMARY
    mock_fetch.assert_not_called()


def test_stale_fallback_on_fetch_failure_preserves_last_good() -> None:
    cfg = _cfg(cache_ttl_seconds=10, stale_fallback_max_age_seconds=900, openai_enabled=False)
    old_cache = {
        "summary": GOOD_SUMMARY,
        "openai": None,
        "fetched_at": time.time() - 60,
        "next_retry_at": 0,
        "_version": cache_mod.CACHE_VERSION,
    }
    fake_usage = ClaudeUsage(available=False, error="http 429: rate limited", retry_after_seconds=272)

    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "read_raw", return_value=old_cache), \
         patch.object(cache_mod, "update_retry_at") as mock_update_retry, \
         patch.object(cli_mod, "fetch_claude_usage", return_value=fake_usage):
        summary, openai = cli_mod._build_summary(cfg)

    assert summary["_stale"] is True
    assert "rate limited" in summary["_stale_reason"] or "429" in summary["_stale_reason"]
    assert summary["five_hour_pct"] == 42.0
    assert summary["seven_day_pct"] == 15.0
    assert summary["_retry_at"] > time.time()
    mock_update_retry.assert_called_once()


def test_rate_limit_backoff_skips_fetch() -> None:
    cfg = _cfg(cache_ttl_seconds=10, stale_fallback_max_age_seconds=900, openai_enabled=False)
    backoff_cache = {
        "summary": GOOD_SUMMARY,
        "openai": None,
        "fetched_at": time.time() - 60,
        "next_retry_at": time.time() + 200,
        "_version": cache_mod.CACHE_VERSION,
    }

    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "read_raw", return_value=backoff_cache), \
         patch.object(cli_mod, "fetch_claude_usage") as mock_fetch:
        summary, _ = cli_mod._build_summary(cfg)

    assert summary["_stale"] is True
    assert summary["_stale_reason"] == "rate-limit backoff"
    mock_fetch.assert_not_called()


def test_no_cache_and_fetch_fails_returns_error() -> None:
    cfg = _cfg(cache_ttl_seconds=10, openai_enabled=False)
    fake_usage = ClaudeUsage(available=False, error="network down")

    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "read_raw", return_value=None), \
         patch.object(cli_mod, "fetch_claude_usage", return_value=fake_usage):
        summary, _ = cli_mod._build_summary(cfg)

    assert summary["available"] is False
    assert summary["error"] == "network down"
    assert summary.get("_stale") is not True
