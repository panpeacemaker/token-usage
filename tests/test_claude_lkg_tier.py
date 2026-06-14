from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from token_usage import cache as cache_mod
from token_usage import cli as cli_mod
from token_usage import config as config_mod
from token_usage.claude import authoritative as authoritative_mod
from token_usage.claude import local_summary as local_summary_mod
from token_usage.claude import oauth_usage as oauth_mod
from token_usage.claude import statusline as statusline_mod
from token_usage.claude.models import ClaudeUsage


def _cfg(**overrides):
    cfg = config_mod.Config()
    overrides.setdefault("kimi_enabled", False)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _bad_oauth(error: str = "http 429") -> ClaudeUsage:
    return ClaudeUsage(available=False, error=error)


def _good_local(five_pct: float = 10.0, seven_pct: float = 5.0) -> tuple[ClaudeUsage, dict]:
    now = datetime.now(timezone.utc)
    return (
        ClaudeUsage(
            available=True,
            five_hour_pct=five_pct,
            five_hour_resets_at=now + timedelta(hours=4),
            seven_day_pct=seven_pct,
            seven_day_resets_at=now + timedelta(days=6),
            subscription_type="local",
            rate_limit_tier="max5",
        ),
        {"total_entries": 42},
    )


def _empty_local() -> tuple[ClaudeUsage, dict]:
    return ClaudeUsage(available=False, error="no local JSONL entries"), {"total_entries": 0}


def _lkg_usage(five_pct: float = 25.0, seven_pct: float = 10.0) -> ClaudeUsage:
    now = datetime.now(timezone.utc)
    return ClaudeUsage(
        available=True,
        five_hour_pct=five_pct,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=seven_pct,
        seven_day_resets_at=now + timedelta(days=3),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )


def _run(cfg, *, statusline=None, oauth=None, local=None, lkg=None):
    if oauth is None:
        oauth = _bad_oauth()
    if local is None:
        local = _good_local()
    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(authoritative_mod, "load", return_value=lkg),
        patch.object(authoritative_mod, "save"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=statusline),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time() if statusline is not None else None),
        patch.object(oauth_mod, "fetch_usage", return_value=oauth),
        patch.object(local_summary_mod, "compute_local", return_value=local),
        patch.object(cli_mod, "_fetch_openai", return_value=None),
        patch.object(cli_mod, "_fetch_kimi", return_value=None),
        patch.object(cli_mod, "_fetch_opencode", return_value=None),
        patch.object(cli_mod, "_fetch_opencode_go", return_value=None),
    ):
        return cli_mod._build_summary(cfg)


def test_lkg_valid_preferred_over_local_estimate() -> None:
    """LKG (real, slightly stale) outranks the local JSONL estimate: a recent real
    OAuth/statusline reading is more trustworthy than the cache-read-weighted local
    approximation (which can be several times off the dashboard)."""
    cfg = _cfg(cache_ttl_seconds=0)
    lkg = (_lkg_usage(25.0, 10.0), "oauth", time.time())
    stale = ClaudeUsage(
        available=True,
        five_hour_pct=99.0,
        five_hour_resets_at=datetime.now(timezone.utc) - timedelta(hours=1),
        seven_day_pct=99.0,
        seven_day_resets_at=datetime.now(timezone.utc) - timedelta(days=1),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )
    summary, _o, _k, _e, _g = _run(cfg, statusline=stale, lkg=lkg, local=_good_local())

    assert summary["_source"] == "lkg"
    assert summary["_source_detail"]["chosen"] == "lkg"
    assert summary["five_hour_pct"] == 25.0
    assert summary["seven_day_pct"] == 10.0
    assert summary.get("_stale") is True
    assert "oauth failed" in summary.get("_stale_reason", "")
    assert summary.get("_fetched_at") == lkg[2]
    rej = summary["_source_detail"]["rejected"]
    assert rej[0]["source"] == "oauth"
    # LKG won before local was reached → local is not in the rejected chain.
    assert all(r["source"] != "local" for r in rej)


def test_lkg_partial_five_expired_marks_five_as_estimate() -> None:
    """When local is unavailable, an expired LKG window is shown but marked estimate."""
    cfg = _cfg(cache_ttl_seconds=0)
    now = datetime.now(timezone.utc)
    lkg_usage = ClaudeUsage(
        available=True,
        five_hour_pct=25.0,
        five_hour_resets_at=now - timedelta(minutes=1),
        seven_day_pct=10.0,
        seven_day_resets_at=now + timedelta(days=3),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )
    lkg = (lkg_usage, "oauth", time.time())
    summary, _o, _k, _e, _g = _run(cfg, statusline=None, lkg=lkg, local=_empty_local())

    assert summary["_source"] == "lkg"
    assert summary["five_hour_pct"] == 25.0
    assert summary["seven_day_pct"] == 10.0
    assert summary.get("_five_hour_estimate") is True
    assert summary.get("_seven_day_estimate") is not True


def test_local_estimate_used_when_lkg_expired() -> None:
    """When LKG windows are both expired (no fresh real source available), the
    local JSONL aggregation is the last-resort fallback — and is flagged as an
    ESTIMATE so the bar never presents it as an authoritative number."""
    cfg = _cfg(cache_ttl_seconds=0)
    now = datetime.now(timezone.utc)
    lkg_usage = ClaudeUsage(
        available=True,
        five_hour_pct=25.0,
        five_hour_resets_at=now - timedelta(hours=1),
        seven_day_pct=10.0,
        seven_day_resets_at=now - timedelta(days=1),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )
    lkg = (lkg_usage, "oauth", time.time())
    summary, _o, _k, _e, _g = _run(cfg, statusline=None, lkg=lkg, local=_good_local())

    assert summary["_source"] == "local"
    assert summary["_source_detail"]["chosen"] == "local"
    assert summary.get("_five_hour_estimate") is True
    assert summary.get("_seven_day_estimate") is True
    assert summary.get("_stale") is not True
    # LKG is evaluated and rejected (windows expired) BEFORE local is chosen.
    assert any(r["source"] == "lkg" for r in summary["_source_detail"]["rejected"])


def test_lkg_both_expired_and_no_local_yields_none() -> None:
    """Local unavailable + LKG both windows expired + no statusline -> none."""
    cfg = _cfg(cache_ttl_seconds=0)
    now = datetime.now(timezone.utc)
    lkg_usage = ClaudeUsage(
        available=True,
        five_hour_pct=25.0,
        five_hour_resets_at=now - timedelta(hours=1),
        seven_day_pct=10.0,
        seven_day_resets_at=now - timedelta(days=1),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )
    lkg = (lkg_usage, "oauth", time.time())
    summary, _o, _k, _e, _g = _run(cfg, statusline=None, lkg=lkg, local=_empty_local())

    assert summary["_source"] == "none"
    rej = summary["_source_detail"]["rejected"]
    assert any(r["source"] == "lkg" and "window expired" in r["reason"] for r in rej)
