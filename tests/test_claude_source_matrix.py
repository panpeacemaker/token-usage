from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from token_usage import cli as cli_mod
from token_usage import cache as cache_mod
from token_usage import config as config_mod
from token_usage.claude import local_summary as local_summary_mod
from token_usage.claude import oauth_usage as oauth_mod
from token_usage.claude import statusline as statusline_mod
from token_usage.claude.models import ClaudeUsage


def _cfg(**overrides):
    cfg = config_mod.Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _fresh_statusline() -> ClaudeUsage:
    now = datetime.now(timezone.utc)
    return ClaudeUsage(
        available=True,
        five_hour_pct=42.0,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=15.0,
        seven_day_resets_at=now + timedelta(days=3),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )


def _stale_statusline() -> ClaudeUsage:
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


def _good_oauth() -> ClaudeUsage:
    now = datetime.now(timezone.utc)
    return ClaudeUsage(
        available=True,
        five_hour_pct=50.0,
        five_hour_resets_at=now + timedelta(hours=3),
        seven_day_pct=20.0,
        seven_day_resets_at=now + timedelta(days=4),
        subscription_type="claude-max",
        rate_limit_tier="oauth",
    )


def _bad_oauth(error: str = "http 429") -> ClaudeUsage:
    return ClaudeUsage(available=False, error=error)


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


def _empty_local() -> tuple[ClaudeUsage, dict]:
    return ClaudeUsage(available=False, error="no local JSONL entries"), {"total_entries": 0}


@pytest.mark.parametrize(
    "statusline_state, oauth_state, local_state, expected_source, expected_rejected_count",
    [
        # statusline fresh → always chosen regardless of oauth/local
        ("fresh", "ok", "ok", "statusline", 0),
        ("fresh", "ok", "empty", "statusline", 0),
        ("fresh", "fail", "ok", "statusline", 0),
        ("fresh", "fail", "empty", "statusline", 0),
        # statusline stale → oauth ok wins
        ("stale", "ok", "ok", "oauth", 1),
        ("stale", "ok", "empty", "oauth", 1),
        # statusline stale → oauth fail, local ok wins
        ("stale", "fail", "ok", "local", 2),
        # statusline stale → oauth fail, local empty → stale statusline fallback
        ("stale", "fail", "empty", "statusline-stale", 3),
        # statusline missing → oauth ok wins
        ("missing", "ok", "ok", "oauth", 1),
        ("missing", "ok", "empty", "oauth", 1),
        # statusline missing → oauth fail, local ok wins
        ("missing", "fail", "ok", "local", 2),
        # statusline missing → oauth fail, local empty → none/error
        ("missing", "fail", "empty", "none", 3),
    ],
)
def test_claude_source_selection_matrix(
    statusline_state, oauth_state, local_state, expected_source, expected_rejected_count
) -> None:
    """Full coverage of _select_claude_source decision matrix."""
    cfg = _cfg(cache_ttl_seconds=0)

    if statusline_state == "fresh":
        sl = _fresh_statusline()
        sl_mtime = time.time()
    elif statusline_state == "stale":
        sl = _stale_statusline()
        sl_mtime = time.time()  # file is fresh but windows expired
    else:
        sl = None
        sl_mtime = None

    oauth = _good_oauth() if oauth_state == "ok" else _bad_oauth()
    local_usage, local_detail = _good_local() if local_state == "ok" else _empty_local()

    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=sl),
        patch.object(cli_mod, "_statusline_mtime", return_value=sl_mtime),
        patch.object(oauth_mod, "fetch_usage", return_value=oauth),
        patch.object(local_summary_mod, "compute_local", return_value=(local_usage, local_detail)),
        patch.object(cli_mod, "_fetch_openai", return_value=None),
        patch.object(cli_mod, "_fetch_kimi", return_value=None),
        patch.object(cli_mod, "_fetch_opencode", return_value=None),
        patch.object(cli_mod, "_fetch_opencode_go", return_value=None),
    ):
        summary, _o, _k, _e, _g = cli_mod._build_summary(cfg)

    assert summary["_source"] == expected_source
    assert summary["_source_detail"]["chosen"] == expected_source
    assert len(summary["_source_detail"]["rejected"]) == expected_rejected_count

    # Verify rejected sources have sensible reasons
    rejected = summary["_source_detail"]["rejected"]
    if statusline_state == "missing":
        assert any(r["source"] == "statusline" and "missing" in r["reason"] for r in rejected)
    elif statusline_state == "stale":
        assert any(r["source"] == "statusline" and "expired" in r["reason"] for r in rejected)

    if oauth_state == "fail" and statusline_state != "fresh":
        assert any(r["source"] == "oauth" and "429" in r["reason"] for r in rejected)

    if local_state == "empty" and statusline_state != "fresh" and oauth_state == "fail":
        assert any(r["source"] == "local" and "no local JSONL" in r["reason"] for r in rejected)


# ---------------------------------------------------------------------------
# Gap-filling: statusline stale + oauth fail + local ok (the one combo not
# explicitly covered in test_cli_hybrid.py).
# ---------------------------------------------------------------------------


def test_stale_statusline_oauth_fail_local_ok() -> None:
    """Specific regression: stale statusline with working local must fall back to local."""
    cfg = _cfg(cache_ttl_seconds=0)
    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=_stale_statusline()),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time()),
        patch.object(oauth_mod, "fetch_usage", return_value=_bad_oauth("timeout")),
        patch.object(local_summary_mod, "compute_local", return_value=_good_local()),
    ):
        summary, _o, _k, _e, _g = cli_mod._build_summary(cfg)

    assert summary["_source"] == "local"
    assert summary["_source_detail"]["chosen"] == "local"
    rej = summary["_source_detail"]["rejected"]
    assert rej[0]["source"] == "statusline"
    assert "expired" in rej[0]["reason"]
    assert rej[1] == {"source": "oauth", "reason": "timeout"}
    assert summary["five_hour_pct"] == 10.0


# ---------------------------------------------------------------------------
# Partial expiry: statusline valid but 5h window expired, 7d still valid
# ---------------------------------------------------------------------------


def test_statusline_fresh_but_five_hour_expired_seven_valid() -> None:
    """Valid statusline with only 5h expired must still be chosen, with 7d driving bar."""
    cfg = _cfg(cache_ttl_seconds=0)
    now = datetime.now(timezone.utc)
    partial = ClaudeUsage(
        available=True,
        five_hour_pct=99.0,
        five_hour_resets_at=now - timedelta(hours=1),
        seven_day_pct=45.0,
        seven_day_resets_at=now + timedelta(days=3),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )
    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=partial),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time()),
        patch.object(oauth_mod, "fetch_usage"),
        patch.object(local_summary_mod, "compute_local", return_value=_good_local()),
    ):
        summary, _o, _k, _e, _g = cli_mod._build_summary(cfg)

    assert summary["_source"] == "statusline"
    assert summary["_source_detail"]["chosen"] == "statusline"
    assert summary.get("_five_hour_expired") is True
    assert summary.get("_seven_day_expired") is not True
    assert summary["five_hour_pct"] == 0.0
    assert summary["seven_day_pct"] == 45.0
