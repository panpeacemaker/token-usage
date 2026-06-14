from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from token_usage import cache as cache_mod
from token_usage import cli as cli_mod
from token_usage import config as config_mod
from token_usage.claude import authoritative as authoritative_mod
from token_usage.claude import local_summary as local_summary_mod
from token_usage.claude import oauth_usage as oauth_mod
from token_usage.claude import statusline as statusline_mod
from token_usage.claude.models import ClaudeUsage

# ---------------------------------------------------------------------------
# Precedence under test:
#   1. OAuth success     - official numbers, saved as last-known-good
#   2. Fresh statusline  - file <600s old + >=1 valid window, saved as LKG
#   3. LKG (valid)       - last real reading, windows unexpired -> marked stale
#   4. Local JSONL       - rough fallback ESTIMATE (marked estimate) when no real
#                          source is available
#   5. Stale statusline  - expired statusline as last resort, marked stale
#   6. None              - nothing usable (available=False)
#
# Rationale: authoritative real numbers (oauth / fresh statusline / valid LKG)
# always beat the local JSONL aggregation, because Anthropic's 5h/7d percentages
# are opaque and the cache-read-weighted local estimate can be several times off
# the real dashboard. Local is a clearly-marked last resort, never authoritative.
# ---------------------------------------------------------------------------


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


def _lkg_valid() -> tuple[ClaudeUsage, str, float]:
    now = datetime.now(timezone.utc)
    return (
        ClaudeUsage(
            available=True,
            five_hour_pct=25.0,
            five_hour_resets_at=now + timedelta(hours=2),
            seven_day_pct=12.0,
            seven_day_resets_at=now + timedelta(days=3),
            subscription_type="claude-max",
            rate_limit_tier="oauth",
        ),
        "oauth",
        time.time(),
    )


def _lkg_expired() -> tuple[ClaudeUsage, str, float]:
    now = datetime.now(timezone.utc)
    return (
        ClaudeUsage(
            available=True,
            five_hour_pct=25.0,
            five_hour_resets_at=now - timedelta(hours=1),
            seven_day_pct=12.0,
            seven_day_resets_at=now - timedelta(days=1),
            subscription_type="claude-max",
            rate_limit_tier="oauth",
        ),
        "oauth",
        time.time(),
    )


@pytest.mark.parametrize(
    "statusline_state, oauth_state, local_state, expected_source, expected_rejected_count",
    [
        # OAuth success always wins (official numbers); nothing rejected before it.
        ("fresh", "ok", "ok", "oauth", 0),
        ("stale", "ok", "ok", "oauth", 0),
        ("fileage", "ok", "ok", "oauth", 0),
        ("missing", "ok", "empty", "oauth", 0),
        # OAuth fails -> a FRESH statusline is the opportunistic override.
        ("fresh", "fail", "ok", "statusline", 1),
        ("fresh", "fail", "empty", "statusline", 1),
        # OAuth fails + statusline not usable + no LKG -> LOCAL estimate fallback
        # (oauth + statusline + lkg-absent are all rejected before local).
        ("stale", "fail", "ok", "local", 3),
        ("fileage", "fail", "ok", "local", 3),
        ("missing", "fail", "ok", "local", 3),
        # OAuth fails + statusline stale + no local + no LKG -> stale statusline last resort.
        ("stale", "fail", "empty", "statusline-stale", 4),
        ("fileage", "fail", "empty", "statusline-stale", 4),
        # OAuth fails + statusline missing + no local + no LKG -> none/error.
        ("missing", "fail", "empty", "none", 4),
    ],
)
def test_claude_source_selection_matrix(
    statusline_state, oauth_state, local_state, expected_source, expected_rejected_count
) -> None:
    """Full coverage of the NEW _select_claude_source decision matrix (no LKG)."""
    cfg = _cfg(cache_ttl_seconds=0)
    now = time.time()

    if statusline_state == "fresh":
        sl = _fresh_statusline()
        sl_mtime = now
    elif statusline_state == "stale":
        sl = _stale_statusline()  # windows expired, file fresh
        sl_mtime = now
    elif statusline_state == "fileage":
        sl = _fresh_statusline()  # windows valid, but file too old
        sl_mtime = now - (statusline_mod.STATUSLINE_MAX_AGE_SECONDS + 100)
    else:  # missing
        sl = None
        sl_mtime = None

    oauth = _good_oauth() if oauth_state == "ok" else _bad_oauth()
    local_usage, local_detail = _good_local() if local_state == "ok" else _empty_local()

    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(authoritative_mod, "load", return_value=None),
        patch.object(authoritative_mod, "save"),
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
    rejected = summary["_source_detail"]["rejected"]
    assert len(rejected) == expected_rejected_count

    # OAuth, when it fails, is ALWAYS the first rejection (it is tier 1 now).
    if oauth_state == "fail":
        assert rejected[0]["source"] == "oauth"
        assert "429" in rejected[0]["reason"]

    # Statusline rejection reason matches its failure mode (only when reached).
    if oauth_state == "fail":
        if statusline_state == "missing":
            assert any(r["source"] == "statusline" and "missing" in r["reason"] for r in rejected)
        elif statusline_state == "stale":
            assert any(r["source"] == "statusline" and "expired" in r["reason"] for r in rejected)
        elif statusline_state == "fileage":
            assert any(r["source"] == "statusline" and "file age" in r["reason"] for r in rejected)

    # Local rejection only when local empty AND reached.
    if oauth_state == "fail" and statusline_state != "fresh" and local_state == "empty":
        assert any(r["source"] == "local" and "no local JSONL" in r["reason"] for r in rejected)

    # Local is a rough fallback ESTIMATE (both windows flagged), not stale.
    if expected_source == "local":
        assert summary.get("_five_hour_estimate") is True
        assert summary.get("_seven_day_estimate") is True
        assert summary.get("_stale") is not True


@pytest.mark.parametrize(
    "oauth_state, statusline_state, local_state, lkg, expected_source",
    [
        # A VALID LKG (real, stale) beats the local estimate.
        ("fail", "missing", "ok", "valid", "lkg"),
        # LKG expired -> local estimate is the last-resort fallback.
        ("fail", "missing", "ok", "expired", "local"),
        # Local unavailable -> a valid LKG is used (marked stale).
        ("fail", "missing", "empty", "valid", "lkg"),
        # Local unavailable + LKG expired + no statusline -> none.
        ("fail", "missing", "empty", "expired", "none"),
        # OAuth success ignores LKG entirely.
        ("ok", "missing", "empty", "valid", "oauth"),
    ],
)
def test_claude_source_with_lkg(oauth_state, statusline_state, local_state, lkg, expected_source) -> None:
    """LKG tier: a valid LKG (real, stale) outranks the local estimate; local is
    used only when LKG is expired/absent, and is then flagged as an estimate."""
    cfg = _cfg(cache_ttl_seconds=0)

    oauth = _good_oauth() if oauth_state == "ok" else _bad_oauth()
    local_usage, local_detail = _good_local() if local_state == "ok" else _empty_local()
    lkg_value = _lkg_valid() if lkg == "valid" else _lkg_expired()

    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(authoritative_mod, "load", return_value=lkg_value),
        patch.object(authoritative_mod, "save"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=None),
        patch.object(cli_mod, "_statusline_mtime", return_value=None),
        patch.object(oauth_mod, "fetch_usage", return_value=oauth),
        patch.object(local_summary_mod, "compute_local", return_value=(local_usage, local_detail)),
        patch.object(cli_mod, "_fetch_openai", return_value=None),
        patch.object(cli_mod, "_fetch_kimi", return_value=None),
        patch.object(cli_mod, "_fetch_opencode", return_value=None),
        patch.object(cli_mod, "_fetch_opencode_go", return_value=None),
    ):
        summary, _o, _k, _e, _g = cli_mod._build_summary(cfg)

    assert summary["_source"] == expected_source
    if expected_source == "local":
        # Local is reached only after a valid LKG was absent/expired (rejected).
        assert summary.get("_stale") is not True
        assert summary.get("_five_hour_estimate") is True
        assert any(r["source"] == "lkg" for r in summary["_source_detail"]["rejected"])
    if expected_source == "lkg":
        assert summary.get("_stale") is True


# ---------------------------------------------------------------------------
# Live-shaped scenario: OAuth 429 + statusline file-age stale + local ok.
# This is the real runtime state (OpenCode user). Local must win with a
# CORRECT pct and full provenance for the rejected remote sources.
# ---------------------------------------------------------------------------


def test_oauth_429_statusline_fileage_stale_local_wins_with_provenance() -> None:
    cfg = _cfg(cache_ttl_seconds=0)
    sl_mtime = time.time() - (statusline_mod.STATUSLINE_MAX_AGE_SECONDS + 254_000)
    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(authoritative_mod, "load", return_value=None),
        patch.object(authoritative_mod, "save"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=_fresh_statusline()),
        patch.object(cli_mod, "_statusline_mtime", return_value=sl_mtime),
        patch.object(oauth_mod, "fetch_usage", return_value=_bad_oauth("http 429: rate limited")),
        patch.object(local_summary_mod, "compute_local", return_value=_good_local()),
    ):
        summary, _o, _k, _e, _g = cli_mod._build_summary(cfg)

    assert summary["_source"] == "local"
    assert summary["five_hour_pct"] == 10.0
    # Local is a rough fallback estimate (flagged), but not "stale".
    assert summary.get("_five_hour_estimate") is True
    assert summary.get("_seven_day_estimate") is True
    assert summary.get("_stale") is not True

    detail = summary["_source_detail"]
    assert detail["chosen"] == "local"
    rej = detail["rejected"]
    assert rej[0] == {"source": "oauth", "reason": "http 429: rate limited"}
    assert rej[1]["source"] == "statusline"
    assert "file age" in rej[1]["reason"]
    assert detail["statusline_age_s"] is not None and detail["statusline_age_s"] > 600


# ---------------------------------------------------------------------------
# Gap-filling: statusline stale + oauth fail + local ok -> local (no LKG).
# ---------------------------------------------------------------------------


def test_stale_statusline_oauth_fail_local_ok() -> None:
    """Stale statusline + failing oauth + working local must use local (authoritative)."""
    cfg = _cfg(cache_ttl_seconds=0)
    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(authoritative_mod, "load", return_value=None),
        patch.object(authoritative_mod, "save"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=_stale_statusline()),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time()),
        patch.object(oauth_mod, "fetch_usage", return_value=_bad_oauth("timeout")),
        patch.object(local_summary_mod, "compute_local", return_value=_good_local()),
    ):
        summary, _o, _k, _e, _g = cli_mod._build_summary(cfg)

    assert summary["_source"] == "local"
    assert summary["_source_detail"]["chosen"] == "local"
    rej = summary["_source_detail"]["rejected"]
    assert rej[0] == {"source": "oauth", "reason": "timeout"}
    assert rej[1]["source"] == "statusline"
    assert "expired" in rej[1]["reason"]
    assert summary["five_hour_pct"] == 10.0
    # Local is a rough fallback estimate — both windows flagged.
    assert summary.get("_five_hour_estimate") is True
    assert summary.get("_seven_day_estimate") is True


# ---------------------------------------------------------------------------
# Partial expiry: statusline valid (fresh file) but 5h window expired, 7d valid.
# Reached only when oauth fails (oauth is tier 1).
# ---------------------------------------------------------------------------


def test_statusline_fresh_but_five_hour_expired_seven_valid() -> None:
    """Valid statusline with only 5h expired must still be chosen, 7d driving bar."""
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
        patch.object(authoritative_mod, "load", return_value=None),
        patch.object(authoritative_mod, "save"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=partial),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time()),
        patch.object(oauth_mod, "fetch_usage", return_value=_bad_oauth("http 429")),
        patch.object(local_summary_mod, "compute_local", return_value=_good_local()),
    ):
        summary, _o, _k, _e, _g = cli_mod._build_summary(cfg)

    assert summary["_source"] == "statusline"
    assert summary["_source_detail"]["chosen"] == "statusline"
    assert summary.get("_five_hour_expired") is True
    assert summary.get("_seven_day_expired") is not True
    assert summary["five_hour_pct"] == 0.0
    assert summary["seven_day_pct"] == 45.0
