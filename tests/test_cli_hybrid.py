from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from token_usage.claude.models import ClaudeUsage

cli_mod = importlib.import_module("token_usage.cli")
cache_mod = importlib.import_module("token_usage.cache")
config_mod = importlib.import_module("token_usage.config")
statusline_mod = importlib.import_module("token_usage.claude.statusline")
local_summary_mod = importlib.import_module("token_usage.claude.local_summary")
oauth_mod = importlib.import_module("token_usage.claude.oauth_usage")


def _cfg(**overrides):
    cfg = config_mod.Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _future_usage(source: str = "statusline") -> ClaudeUsage:
    now = datetime.now(timezone.utc)
    return ClaudeUsage(
        available=True,
        five_hour_pct=42.0,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=15.0,
        seven_day_resets_at=now + timedelta(days=3),
        subscription_type=source,
        rate_limit_tier=source,
    )


def _past_usage() -> ClaudeUsage:
    now = datetime.now(timezone.utc)
    return ClaudeUsage(
        available=True,
        five_hour_pct=99.0,
        five_hour_resets_at=now - timedelta(hours=1),
        seven_day_pct=99.0,
        seven_day_resets_at=now - timedelta(days=1),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )


def _empty_local() -> tuple[ClaudeUsage, dict]:
    return ClaudeUsage(available=False, error="no local JSONL entries"), {"total_entries": 0}


def _good_local() -> tuple[ClaudeUsage, dict]:
    now = datetime.now(timezone.utc)
    return (
        ClaudeUsage(
            available=True,
            five_hour_pct=10.0,
            five_hour_resets_at=now + timedelta(hours=4),
            seven_day_pct=5.0,
            seven_day_resets_at=now + timedelta(days=6),
            subscription_type="local",
            rate_limit_tier="max5",
        ),
        {"total_entries": 42},
    )


def _oauth_unavailable(error: str = "http 429") -> ClaudeUsage:
    return ClaudeUsage(available=False, error=error)


def test_fresh_output_cache_short_circuits() -> None:
    cfg = _cfg(cache_ttl_seconds=300, openai_enabled=False)
    cached = {"summary": {"available": True, "five_hour_pct": 55}, "openai": None}
    with patch.object(cache_mod, "read", return_value=cached), \
         patch.object(statusline_mod, "read_statusline_usage") as mock_sl, \
         patch.object(oauth_mod, "fetch_usage") as mock_oauth, \
         patch.object(local_summary_mod, "compute_local") as mock_local:
        summary, _ = cli_mod._build_summary(cfg)
    assert summary["five_hour_pct"] == 55
    mock_sl.assert_not_called()
    mock_oauth.assert_not_called()
    mock_local.assert_not_called()


def test_statusline_primary_when_valid_skips_oauth() -> None:
    cfg = _cfg(cache_ttl_seconds=0, openai_enabled=False)
    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "write"), \
         patch.object(statusline_mod, "read_statusline_usage", return_value=_future_usage("statusline")), \
         patch.object(oauth_mod, "fetch_usage") as mock_oauth, \
         patch.object(local_summary_mod, "compute_local", return_value=_good_local()):
        summary, _ = cli_mod._build_summary(cfg)
    assert summary["_source"] == "statusline"
    assert summary["five_hour_pct"] == 42.0
    mock_oauth.assert_not_called()


def test_oauth_when_statusline_missing() -> None:
    cfg = _cfg(cache_ttl_seconds=0, openai_enabled=False)
    oauth_result = _future_usage("oauth")
    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "write"), \
         patch.object(statusline_mod, "read_statusline_usage", return_value=None), \
         patch.object(oauth_mod, "fetch_usage", return_value=oauth_result), \
         patch.object(local_summary_mod, "compute_local", return_value=_good_local()):
        summary, _ = cli_mod._build_summary(cfg)
    assert summary["_source"] == "oauth"
    assert summary["five_hour_pct"] == 42.0
    assert summary["subscription_type"] == "oauth"


def test_oauth_when_statusline_window_expired() -> None:
    cfg = _cfg(cache_ttl_seconds=0, openai_enabled=False)
    oauth_result = _future_usage("oauth")
    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "write"), \
         patch.object(statusline_mod, "read_statusline_usage", return_value=_past_usage()), \
         patch.object(oauth_mod, "fetch_usage", return_value=oauth_result), \
         patch.object(local_summary_mod, "compute_local", return_value=_good_local()):
        summary, _ = cli_mod._build_summary(cfg)
    assert summary["_source"] == "oauth"


def test_local_fallback_when_oauth_fails() -> None:
    cfg = _cfg(cache_ttl_seconds=0, openai_enabled=False)
    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "write"), \
         patch.object(statusline_mod, "read_statusline_usage", return_value=None), \
         patch.object(oauth_mod, "fetch_usage", return_value=_oauth_unavailable("http 429")), \
         patch.object(local_summary_mod, "compute_local", return_value=_good_local()):
        summary, _ = cli_mod._build_summary(cfg)
    assert summary["_source"] == "local"
    assert summary["five_hour_pct"] == 10.0


def test_stale_statusline_returned_when_oauth_fails_and_no_local() -> None:
    cfg = _cfg(cache_ttl_seconds=0, openai_enabled=False)
    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "write"), \
         patch.object(statusline_mod, "read_statusline_usage", return_value=_past_usage()), \
         patch.object(oauth_mod, "fetch_usage", return_value=_oauth_unavailable()), \
         patch.object(local_summary_mod, "compute_local", return_value=_empty_local()):
        summary, _ = cli_mod._build_summary(cfg)
    assert summary["_source"] == "statusline-stale"
    assert summary["five_hour_pct"] == 99.0


def test_everything_empty_returns_unavailable() -> None:
    cfg = _cfg(cache_ttl_seconds=0, openai_enabled=False)
    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "write"), \
         patch.object(statusline_mod, "read_statusline_usage", return_value=None), \
         patch.object(oauth_mod, "fetch_usage", return_value=_oauth_unavailable("credentials not found")), \
         patch.object(local_summary_mod, "compute_local", return_value=_empty_local()):
        summary, _ = cli_mod._build_summary(cfg)
    assert summary["_source"] == "none"
    assert summary["available"] is False
    assert "credentials not found" in summary["error"]


def test_build_summary_writes_cache() -> None:
    cfg = _cfg(cache_ttl_seconds=0, openai_enabled=False)
    with patch.object(cache_mod, "read", return_value=None), \
         patch.object(cache_mod, "write") as mock_write, \
         patch.object(statusline_mod, "read_statusline_usage", return_value=_future_usage()), \
         patch.object(oauth_mod, "fetch_usage"), \
         patch.object(local_summary_mod, "compute_local", return_value=_good_local()):
        cli_mod._build_summary(cfg)
    mock_write.assert_called_once()
    payload = mock_write.call_args[0][0]
    assert "summary" in payload
    assert "openai" in payload
