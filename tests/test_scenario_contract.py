"""Binding correctness contract: the 7 named scenarios (S1-S7).

Each test formalizes one scenario's binary pass condition end-to-end. These are
the load-bearing invariants of the token-usage CLI; if any test here FAILS, the
underlying behavior is a real defect — do not weaken the assertion.

Helpers/fixtures are replicated minimally from the existing suites
(test_golden_e2e.py, test_statusbar_detail_consistency.py,
test_claude_source_matrix.py, test_opencode_usage_provider.py) so this file
exercises the same data shapes and seams.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from token_usage import _normalize
from token_usage import cache as cache_mod
from token_usage import cli as cli_mod
from token_usage import config as config_mod
from token_usage.claude import aggregator
from token_usage.claude import authoritative as authoritative_mod
from token_usage.claude import local_summary as local_summary_mod
from token_usage.claude import oauth_usage as oauth_mod
from token_usage.claude import opencode_reader as oc_reader_mod
from token_usage.claude import reader as reader_mod
from token_usage.claude import statusline as statusline_mod
from token_usage.claude.limits import get_limits
from token_usage.claude.models import ClaudeUsage, UsageEntry
from token_usage.formatters import detail, statusbar
from token_usage.opencode.usage import fetch_opencode

# Fixed-calendar anchor reused across the opencode fixtures (mirrors the
# existing provider tests). NOW = 2026-04-28 18:13:20 UTC (Tuesday).
NOW = 1_777_400_000

# Far-future resets so direct-dict fixtures never trip the normalize cutoff.
RESET_5H = datetime(2099, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
RESET_7D = datetime(2099, 4, 13, 20, 0, 0, tzinfo=timezone.utc)
PRIMARY_RESET = 4_081_503_240
WEEKLY_RESET = 4_082_100_040
MONTHLY_RESET = 4_083_000_000


# ---------------------------------------------------------------------------
# Cross-formatter helpers (statusbar pct vs detail "← bar" pct)
# ---------------------------------------------------------------------------

def _sb_pct(text: str, letter: str) -> float:
    """Percentage of a provider's statusbar segment, found by its letter."""
    m = re.search(rf"{letter}(\d+(?:\.\d+)?)%", text)
    assert m, f"no {letter!r} pct found in statusbar: {text!r}"
    return float(m.group(1))


def _section(detail_text: str, needle: str) -> str:
    """The blank-line-delimited detail section containing ``needle``."""
    for section in detail_text.split("\n\n"):
        if needle in section:
            return section
    raise AssertionError(f"no detail section containing {needle!r}")


def _bar_pct(section: str) -> float:
    """Percentage of the window marked ``← bar`` within a detail section."""
    for line in section.split("\n"):
        if "← bar" in line:
            m = re.search(r"(\d+(?:\.\d+)?)%", line)
            assert m, f"no pct found on bar line: {line!r}"
            return float(m.group(1))
    raise AssertionError(f"no '← bar' marker in section:\n{section}")


# ---------------------------------------------------------------------------
# OpenCode SQLite helpers (replicated minimally from test_golden_e2e.py)
# ---------------------------------------------------------------------------

def _create_opencode_db(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    return conn


def _insert_opencode(conn: sqlite3.Connection, msg_id: str, ts_ms: int, data: dict) -> None:
    conn.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
        (msg_id, "ses_test", ts_ms, ts_ms, json.dumps(data)),
    )


def _opencode_msg(input_t: int = 0, output_t: int = 0, provider: str = "opencode") -> dict:
    tokens = {"input": input_t, "output": output_t, "cache": {"read": 0, "write": 0}}
    return {"role": "assistant", "providerID": provider, "modelID": "claude-sonnet-4-6", "tokens": tokens}


# ---------------------------------------------------------------------------
# Claude source fixtures (replicated minimally from test_claude_source_matrix.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Claude aggregator fixtures (replicated minimally from test_aggregator.py)
# ---------------------------------------------------------------------------

def _agg_entry(ts: datetime, msg_id: str, tokens: int, kind: str = "turn") -> UsageEntry:
    return UsageEntry(ts, msg_id, "req", "claude-sonnet-4-6", tokens, 0, 0, 0, kind)


# ===========================================================================
# S1 — statusbar pct of every ACTIVE provider matches its detail "← bar" pct,
#      while an idle provider renders idle (not a phantom 0%).
# ===========================================================================

def test_s1_statusbar_active_providers_match_detail_bar() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 80.0,  # 7d drives
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    openai = {
        "available": True,
        "primary_pct": 40.0,
        "primary_reset_at": PRIMARY_RESET,
        "weekly_pct": 90.0,  # weekly drives
        "weekly_reset_at": WEEKLY_RESET,
    }
    kimi = {
        "available": True,
        "primary_pct": 20.0,
        "primary_reset_at": PRIMARY_RESET,
        "weekly_pct": 55.0,  # weekly drives
        "weekly_reset_at": WEEKLY_RESET,
    }
    opencode_idle = {
        "available": True,
        "provider_id": "opencode",
        "window_kind": "fixed",
        "is_idle": True,
        "primary_pct": 0.0,
        "primary_reset_at": PRIMARY_RESET,
        "weekly_pct": 0.0,
        "weekly_reset_at": WEEKLY_RESET,
        "monthly_pct": 3.0,
        "monthly_reset_at": MONTHLY_RESET,
        "monthly_tokens": 3000,
        "monthly_limit_tokens": 100000,
    }
    opencode_go = {
        "available": True,
        "provider_id": "opencode-go",
        "window_kind": "fixed",
        "is_idle": False,
        "primary_pct": 70.0,  # 5h drives
        "primary_reset_at": PRIMARY_RESET,
        "weekly_pct": 10.0,
        "weekly_reset_at": WEEKLY_RESET,
        "monthly_pct": 5.0,
        "monthly_reset_at": MONTHLY_RESET,
        "monthly_limit_tokens": 100000,
    }

    sb = statusbar.format_compact(summary, openai, kimi, opencode_idle, opencode_go)
    det = detail.format_detail(summary, openai, kimi, opencode_idle, opencode_go)

    # Idle opencode renders `e idle`, never a phantom percentage / bar.
    assert "e idle" in sb
    assert "e0%" not in sb
    zen_section = _section(det, "(opencode)")
    assert "idle" in zen_section
    assert "← bar" not in zen_section

    # Every NON-idle provider: statusbar pct == its detail `← bar` window pct.
    for letter, needle in (("c", "Claude ("), ("o", "ChatGPT"), ("k", "Kimi"), ("g", "(opencode-go)")):
        assert _sb_pct(sb, letter) == _bar_pct(_section(det, needle)), f"mismatch for {letter!r}"


# ===========================================================================
# S2 — Claude: OAuth 429 + stale statusline. The tool surfaces the last REAL
#      reading (LKG, OAuth-origin) marked stale, with full provenance — it does
#      NOT fall to the unreliable cache-read-weighted local estimate. This is the
#      trust-critical case: a real-but-old number beats a fresh-but-wrong one.
# ===========================================================================

def test_s2_claude_authoritative_source_with_provenance() -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    now = datetime.now(timezone.utc)
    lkg_usage = ClaudeUsage(
        available=True,
        five_hour_pct=31.0,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=9.0,
        seven_day_resets_at=now + timedelta(days=3),
        subscription_type="claude-max",
        rate_limit_tier="oauth",
    )

    with (
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(authoritative_mod, "load", return_value=(lkg_usage, "oauth", time.time())),
        patch.object(authoritative_mod, "save"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=_stale_statusline()),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time()),
        patch.object(oauth_mod, "fetch_usage", return_value=ClaudeUsage(available=False, error="http 429: rate limited")),
        patch.object(local_summary_mod, "compute_local", return_value=_good_local()),
        patch.object(cli_mod, "_fetch_openai", return_value=None),
        patch.object(cli_mod, "_fetch_kimi", return_value=None),
        patch.object(cli_mod, "_fetch_opencode", return_value=None),
        patch.object(cli_mod, "_fetch_opencode_go", return_value=None),
    ):
        summary, _o, _k, _e, _g = cli_mod._build_summary(cfg)

    # LKG (real, OAuth-origin) wins — NOT the local estimate (10.0).
    assert summary["_source"] == "lkg"
    assert summary["five_hour_pct"] == 31.0
    assert summary["seven_day_pct"] == 9.0

    # Provenance names the rejected live sources, in order.
    sd = summary["_source_detail"]
    assert sd["chosen"] == "lkg"
    rej = sd["rejected"]
    assert rej[0]["source"] == "oauth"
    assert "429" in rej[0]["reason"]
    assert rej[1]["source"] == "statusline"
    assert "expired" in rej[1]["reason"]
    # The local estimate was never reached (real LKG outranks it).
    assert all(r["source"] != "local" for r in rej)

    # LKG is real but old → marked stale (honest), not presented as live.
    assert summary.get("_stale") is True

    # Rendered detail names the winning source.
    det = detail.format_detail(summary)
    assert "source: lkg" in det
    assert "oauth: http 429" in det


# ===========================================================================
# S3 — an idle opencode provider renders `e idle` / the idle note, never 0%.
# ===========================================================================

def test_s3_idle_provider_renders_idle_not_zero(tmp_path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_opencode_db(db)
    # Only monthly-aged activity → primary & weekly tokens 0, monthly > 0 → idle.
    _insert_opencode(conn, "m1", (NOW - 10 * 86400) * 1000, _opencode_msg(input_t=500, provider="opencode"))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=100000,
        now=NOW,
    )
    assert result.is_idle is True
    assert result.primary_tokens == 0
    assert result.weekly_tokens == 0
    assert result.monthly_tokens == 500

    data = _normalize.normalize_windows(asdict(result), _normalize.OPENCODE_WINDOW_FIELDS, now=NOW)

    sb = statusbar.format_compact({}, None, None, data)
    assert sb == "e idle"
    assert "e0%" not in sb

    det = detail.format_detail(None, None, None, data)
    assert "idle — no activity" in det
    assert "0.0%" not in det


# ===========================================================================
# S4 — cross-formatter invariant for the FULL 5-provider matrix: every
#      provider's statusbar pct equals its detail `← bar` window pct.
# ===========================================================================

def test_s4_all_providers_statusbar_equals_detail_bar() -> None:
    # Deliberately fractional pcts: the statusbar renders integers (`{:.0f}`)
    # while detail shows one decimal, so the invariant is "same window + faithful
    # rounding". Whole-number fixtures would mask the rounding relationship.
    summary = {
        "available": True,
        "five_hour_pct": 33.4,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 58.3,  # 7d drives
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    openai = {
        "available": True,
        "primary_pct": 44.4,  # primary drives
        "primary_reset_at": PRIMARY_RESET,
        "weekly_pct": 22.1,
        "weekly_reset_at": WEEKLY_RESET,
    }
    kimi = {
        "available": True,
        "primary_pct": 66.6,  # 5h drives
        "primary_reset_at": PRIMARY_RESET,
        "weekly_pct": 11.2,
        "weekly_reset_at": WEEKLY_RESET,
    }
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "window_kind": "fixed",
        "is_idle": False,
        "primary_pct": 15.0,
        "primary_reset_at": PRIMARY_RESET,
        "weekly_pct": 77.7,  # weekly drives
        "weekly_reset_at": WEEKLY_RESET,
        "monthly_pct": 5.0,
        "monthly_reset_at": MONTHLY_RESET,
        "monthly_limit_tokens": 100000,
    }
    opencode_go = {
        "available": True,
        "provider_id": "opencode-go",
        "window_kind": "fixed",
        "is_idle": False,
        "primary_pct": 19.5,  # 5h drives
        "primary_reset_at": PRIMARY_RESET,
        "weekly_pct": 10.1,
        "weekly_reset_at": WEEKLY_RESET,
        "monthly_pct": 5.0,
        "monthly_reset_at": MONTHLY_RESET,
        "monthly_limit_tokens": 100000,
    }

    sb = statusbar.format_compact(summary, openai, kimi, opencode, opencode_go)
    det = detail.format_detail(summary, openai, kimi, opencode, opencode_go)

    for letter, needle in (
        ("c", "Claude ("),
        ("o", "ChatGPT"),
        ("k", "Kimi"),
        ("e", "(opencode)"),
        ("g", "(opencode-go)"),
    ):
        bar_pct = _bar_pct(_section(det, needle))
        assert _sb_pct(sb, letter) == round(bar_pct), f"mismatch for {letter!r}"


# ===========================================================================
# S5 — no phantom >100%: the old tool/sidechain message overcount is gone
#      (pct_messages ≤ 100), but a genuine over-limit token pct stays visible.
# ===========================================================================

def test_s5_no_phantom_over_100_pct() -> None:
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    limits = get_limits("pro")

    # One real user turn fans out into many tool-call / sidechain API records.
    # Old code counted all 2358 as "messages" (phantom >100%); only real turns
    # may count now.
    entries: list[UsageEntry] = []
    for i in range(2346):
        kind = "tool" if i % 2 == 0 else "sidechain"
        entries.append(_agg_entry(now - timedelta(minutes=2), f"x{i}", 1000, kind))
    for i in range(12):
        entries.append(_agg_entry(now - timedelta(minutes=1), f"t{i}", 1000, "turn"))

    s = aggregator.summarize(entries, limits, now=now)
    assert s["total_entries"] == 2358
    assert s["week"]["messages"] == 12  # phantom 2358 gone — only real turns
    assert s["week"]["pct_messages"] <= 100

    # Genuine over-limit (tokens > limit) MUST still render >100% — no blanket
    # clamp that hides real overage.
    over_limits = get_limits("pro", {"pro": {"tokens_weekly": 1000}})
    over_entries = [_agg_entry(now - timedelta(days=1), "big", 5000, "turn")]
    so = aggregator.summarize(over_entries, over_limits, now=now)
    assert so["week"]["tokens"] == 5000
    assert so["week"]["pct"] > 100


# ===========================================================================
# S6 — a missing/renamed required token field makes a provider render `err`
#      (statusbar) / `unavailable` (detail), never a silent 0%.
# ===========================================================================

def test_s6_missing_token_field_renders_err(tmp_path) -> None:
    # (a) Claude OAuth: the required `five_hour.utilization` field is dropped.
    broken = {"five_hour": {"resets_at": "2026-04-08T02:00:00+00:00"}, "seven_day": {"utilization": 15.0}}
    with (
        patch.object(oauth_mod, "_read_token", return_value=("fake-token", None)),
        patch.object(oauth_mod, "_http_get", return_value=(broken, None)),
    ):
        claude_result = oauth_mod.fetch_usage()

    assert not claude_result.available
    assert "schema: missing five_hour utilization" in claude_result.error

    claude_data = _normalize.normalize_windows(asdict(claude_result), _normalize.OPENAI_WINDOW_FIELDS)
    c_sb = statusbar.format_compact(claude_data)
    assert c_sb == "c err"
    assert "0%" not in c_sb
    c_det = detail.format_detail(claude_data)
    assert claude_result.error in c_det
    assert "unavailable:" in c_det

    # (b) OpenCode: the required token-carrying `data` column is renamed away.
    db = tmp_path / "opencode.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    oc_result = fetch_opencode(db_path=db, primary_limit_tokens=1000, weekly_limit_tokens=10000)
    assert not oc_result.available
    assert "read failed" in oc_result.error

    oc_data = _normalize.normalize_windows(asdict(oc_result), _normalize.OPENCODE_WINDOW_FIELDS)
    e_sb = statusbar.format_compact({}, None, None, oc_data)
    assert e_sb == "e err"
    assert "0%" not in e_sb
    e_det = detail.format_detail(None, None, None, oc_data)
    assert oc_result.error in e_det
    assert "unavailable:" in e_det

    # (c) OpenCode: token sub-fields renamed (input->inputX) while the cache
    # sub-object keeps its zero read/write keys — the realistic drift shape. Real
    # usage now hides under unrecognized keys → must render `err`, not idle/0%.
    db2 = tmp_path / "opencode_renamed_fields.db"
    conn2 = _create_opencode_db(db2)
    for i in range(3):
        bad = {
            "role": "assistant",
            "providerID": "opencode",
            "tokens": {"inputX": 500, "outputX": 200, "cache": {"read": 0, "write": 0}},
        }
        _insert_opencode(conn2, f"b{i}", (NOW - 100) * 1000, bad)
    conn2.commit()
    conn2.close()

    oc2 = fetch_opencode(
        db_path=db2, primary_limit_tokens=1000, weekly_limit_tokens=10000, now=NOW
    )
    assert not oc2.available
    assert oc2.is_idle is False
    assert "token schema" in oc2.error

    oc2_data = _normalize.normalize_windows(asdict(oc2), _normalize.OPENCODE_WINDOW_FIELDS)
    e2_sb = statusbar.format_compact({}, None, None, oc2_data)
    assert e2_sb == "e err"
    assert "e0%" not in e2_sb

    # (d) MIXED good + drifted rows must NOT silently undercount — one malformed
    # row in the window fails the whole provider loud, never a partial pct.
    db3 = tmp_path / "opencode_mixed.db"
    conn3 = _create_opencode_db(db3)
    _insert_opencode(conn3, "good", (NOW - 100) * 1000, _opencode_msg(input_t=150, provider="opencode"))
    _insert_opencode(
        conn3,
        "bad",
        (NOW - 200) * 1000,
        {"role": "assistant", "providerID": "opencode", "tokens": {"inputX": 999, "cache": {"read": 0, "write": 0}}},
    )
    conn3.commit()
    conn3.close()

    oc3 = fetch_opencode(
        db_path=db3, primary_limit_tokens=1000, weekly_limit_tokens=10000, now=NOW
    )
    assert not oc3.available
    assert "token schema" in oc3.error

    # (e) Real usage moved OUT of `tokens` to the alternate top-level `usage`
    # field while `tokens` is left as an all-zero / empty shell. Must fail loud,
    # never silently render idle/0%.
    for label, tok in (("zero_shell", {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}}), ("empty", {})):
        db4 = tmp_path / f"opencode_topusage_{label}.db"
        conn4 = _create_opencode_db(db4)
        _insert_opencode(
            conn4,
            "u1",
            (NOW - 100) * 1000,
            {"role": "assistant", "providerID": "opencode", "tokens": tok, "usage": {"input": 500, "output": 200}},
        )
        conn4.commit()
        conn4.close()
        oc4 = fetch_opencode(db_path=db4, primary_limit_tokens=1000, weekly_limit_tokens=10000, now=NOW)
        assert not oc4.available, label
        assert oc4.is_idle is False, label
        assert "token schema" in oc4.error, label

    # (f) The SQL SELECTOR keys drift: providerID->provider or role->type. The
    # canonical query then matches nothing and the provider would look idle even
    # though real usage exists → must fail loud, never silent idle.
    for label, row in (
        ("provider_renamed", {"role": "assistant", "provider": "opencode", "tokens": {"input": 500, "output": 200, "cache": {"read": 0, "write": 0}}}),
        ("role_renamed", {"type": "assistant", "providerID": "opencode", "tokens": {"input": 500, "output": 200, "cache": {"read": 0, "write": 0}}}),
    ):
        db5 = tmp_path / f"opencode_selector_{label}.db"
        conn5 = _create_opencode_db(db5)
        _insert_opencode(conn5, "s1", (NOW - 100) * 1000, row)
        conn5.commit()
        conn5.close()
        oc5 = fetch_opencode(db_path=db5, primary_limit_tokens=1000, weekly_limit_tokens=10000, now=NOW)
        assert not oc5.available, label
        assert oc5.is_idle is False, label
        assert "selector" in oc5.error, label

    # (f2) MIXED: an old canonical row coexists with a newer drifted row in the
    # window. Selector drift must still fail loud — a surviving canonical row must
    # not suppress detection (else the drifted usage is silently undercounted).
    db_mix = tmp_path / "opencode_selector_mixed.db"
    conn_mix = _create_opencode_db(db_mix)
    _insert_opencode(
        conn_mix, "old", (NOW - 20 * 86400) * 1000,
        {"role": "assistant", "providerID": "opencode", "tokens": {"input": 100, "cache": {"read": 0, "write": 0}}},
    )
    _insert_opencode(
        conn_mix, "new", (NOW - 100) * 1000,
        {"role": "assistant", "provider": "opencode", "tokens": {"input": 900, "cache": {"read": 0, "write": 0}}},
    )
    conn_mix.commit()
    conn_mix.close()
    oc_mix = fetch_opencode(
        db_path=db_mix, primary_limit_tokens=1000, weekly_limit_tokens=10000, monthly_limit_tokens=100000, now=NOW
    )
    assert not oc_mix.available
    assert "selector" in oc_mix.error

    # Guard: a genuinely empty DB must still render idle, NOT a selector error.
    db6 = tmp_path / "opencode_empty.db"
    _create_opencode_db(db6).close()
    oc6 = fetch_opencode(db_path=db6, primary_limit_tokens=1000, weekly_limit_tokens=10000, now=NOW)
    assert oc6.available
    assert oc6.is_idle is True

    # Guard: an all-canonical DB with real usage must NOT trip selector drift.
    db7 = tmp_path / "opencode_canonical_ok.db"
    conn7 = _create_opencode_db(db7)
    _insert_opencode(conn7, "ok", (NOW - 100) * 1000, _opencode_msg(input_t=150, provider="opencode"))
    conn7.commit()
    conn7.close()
    oc7 = fetch_opencode(db_path=db7, primary_limit_tokens=1000, weekly_limit_tokens=10000, now=NOW)
    assert oc7.available
    assert oc7.error is None
    assert oc7.primary_tokens == 150


# ===========================================================================
# S7 — opencode and opencode-go share the identical fixed-calendar reset rule:
#      from the same timestamps, all reset_at values are provider-independent.
# ===========================================================================

def test_s7_zen_go_identical_window_reset_rule(tmp_path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_opencode_db(db)
    for off in (60, 3 * 86400, 10 * 86400):
        _insert_opencode(conn, f"z{off}", (NOW - off) * 1000, _opencode_msg(input_t=111, provider="opencode"))
        _insert_opencode(conn, f"g{off}", (NOW - off) * 1000, _opencode_msg(input_t=111, provider="opencode-go"))
    conn.commit()
    conn.close()

    common = dict(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=100000,
        now=NOW,
    )
    zen = fetch_opencode(provider_id="opencode", **common)
    go = fetch_opencode(provider_id="opencode-go", **common)

    assert zen.primary_reset_at == go.primary_reset_at
    assert zen.weekly_reset_at == go.weekly_reset_at
    assert zen.monthly_reset_at == go.monthly_reset_at


# ===========================================================================
# D4-bar — a real weekly MESSAGE-cap breach must surface on the 7-day bar even
#          when token usage is low (the message limit is a published constraint).
# ===========================================================================

def _jsonl_turn(path, msg_id: str, ts_iso: str, inp: int, stop: str = "end_turn", sidechain: bool = False) -> None:
    rec = {
        "timestamp": ts_iso,
        "requestId": f"req-{msg_id}",
        "isSidechain": sidechain,
        "message": {
            "id": msg_id,
            "model": "claude-sonnet-4-6",
            "stop_reason": stop,
            "usage": {"input_tokens": inp, "output_tokens": 1},
        },
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def test_message_pct_drives_seven_day_bar(tmp_path) -> None:
    jsonl = tmp_path / "turns.jsonl"
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    for i in range(5):
        _jsonl_turn(jsonl, f"m{i}", (now - timedelta(hours=1)).isoformat(), inp=10)

    # messages_weekly=2 → 5 turns = 250%; tokens_weekly huge → token pct ≈ 0.
    limits = get_limits("pro", {"pro": {"messages_weekly": 2, "tokens_weekly": 10_000_000}})
    usage, _detail = local_summary_mod.compute_local(limits, now=now, root=jsonl, opencode_db=tmp_path / "none.db")

    assert usage.available
    assert usage.seven_day_pct >= 250.0  # message breach is visible, not hidden by low token pct


# ===========================================================================
# D3-reader — message-kind classification happens in the READERS from raw
#             records (not just trusted via UsageEntry(kind=...)).
# ===========================================================================

def test_readers_classify_tool_and_sidechain_from_raw_records(tmp_path) -> None:
    jsonl = tmp_path / "mixed.jsonl"
    ts = "2026-04-08T09:00:00+00:00"
    _jsonl_turn(jsonl, "real", ts, inp=10, stop="end_turn")
    _jsonl_turn(jsonl, "toolcall", ts, inp=10, stop="tool_use")
    _jsonl_turn(jsonl, "side", ts, inp=10, stop="end_turn", sidechain=True)

    by_id = {e.message_id: e.kind for e in reader_mod.load_entries(jsonl)}
    assert by_id["real"] == "turn"
    assert by_id["toolcall"] == "tool"
    assert by_id["side"] == "sidechain"

    db = tmp_path / "oc.db"
    conn = _create_opencode_db(db)
    for mid, finish in (("octurn", "stop"), ("octool", "tool-calls")):
        _insert_opencode(
            conn,
            mid,
            (NOW - 100) * 1000,
            {
                "role": "assistant",
                "providerID": "anthropic",
                "modelID": "claude-sonnet-4-6",
                "finish": finish,
                "tokens": {"input": 100, "output": 50, "cache": {"read": 0, "write": 0}},
            },
        )
    conn.commit()
    conn.close()

    oc_kinds = {e.message_id: e.kind for e in oc_reader_mod.load_entries(db)}
    assert oc_kinds["octurn"] == "turn"
    assert oc_kinds["octool"] == "tool"
