from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from token_usage.opencode.usage import OpencodeUsage, fetch_opencode

NOW = 1_777_400_000

# NOW = 2026-04-28 18:13:20 UTC (Tuesday).
# Fixed-calendar window boundaries derived from NOW (all UTC):
NOW_PRIMARY_RESET = 1_777_410_000  # 2026-04-28 21:00:00 (next fixed 5h block)
NOW_WEEKLY_RESET = 1_777_852_800  # 2026-05-04 00:00:00 (next Monday)
NOW_MONTHLY_RESET = 1_777_593_600  # 2026-05-01 00:00:00 (first of next month)
NOW_WEEKLY_START = 1_777_248_000  # 2026-04-27 00:00:00 (this week's Monday)
NOW_MONTHLY_START = 1_775_001_600  # 2026-04-01 00:00:00 (first of month)


def _create_db(path: Path) -> sqlite3.Connection:
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


def _insert(conn: sqlite3.Connection, msg_id: str, ts_ms: int, data: dict) -> None:
    conn.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
        (msg_id, "ses_test", ts_ms, ts_ms, json.dumps(data)),
    )


def _opencode_msg(input_t: int = 0, output_t: int = 0, total: int | None = None, provider: str = "opencode") -> dict:
    tokens: dict = {"input": input_t, "output": output_t, "cache": {"read": 0, "write": 0}}
    if total is not None:
        tokens["total"] = total
    return {
        "role": "assistant",
        "providerID": provider,
        "modelID": "claude-sonnet-4-6",
        "tokens": tokens,
    }


def test_missing_db_returns_unavailable(tmp_path: Path) -> None:
    result = fetch_opencode(db_path=tmp_path / "missing.db", primary_limit_tokens=100, weekly_limit_tokens=1000)
    assert not result.available
    assert "not found" in result.error


def test_zero_limits_returns_unavailable(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    _create_db(db).close()
    result = fetch_opencode(db_path=db, primary_limit_tokens=0, weekly_limit_tokens=0)
    assert not result.available
    assert "limit_tokens" in result.error


def test_only_opencode_provider_counted(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 100) * 1000, _opencode_msg(input_t=500, provider="opencode"))
    _insert(conn, "m2", (NOW - 100) * 1000, _opencode_msg(input_t=999, provider="anthropic"))
    _insert(conn, "m3", (NOW - 100) * 1000, _opencode_msg(input_t=999, provider="github-copilot"))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.available
    assert result.primary_tokens == 500
    assert result.weekly_tokens == 500
    assert result.primary_pct == 50.0


def test_provider_id_opencode_go_isolates_go(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 100) * 1000, _opencode_msg(input_t=300, provider="opencode"))
    _insert(conn, "m2", (NOW - 100) * 1000, _opencode_msg(input_t=700, provider="opencode-go"))
    conn.commit()
    conn.close()

    go = fetch_opencode(
        db_path=db,
        provider_id="opencode-go",
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert go.primary_tokens == 700
    zen = fetch_opencode(
        db_path=db,
        provider_id="opencode",
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert zen.primary_tokens == 300


def test_primary_window_excludes_old_rows(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "old", (NOW - 6 * 3600) * 1000, _opencode_msg(input_t=999))
    _insert(conn, "new", (NOW - 60) * 1000, _opencode_msg(input_t=200))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.primary_tokens == 200
    assert result.weekly_tokens == 1199


def test_weekly_window_excludes_very_old(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "ancient", (NOW - 8 * 86400) * 1000, _opencode_msg(input_t=999))
    _insert(conn, "recent", (NOW - 86400) * 1000, _opencode_msg(input_t=300))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.weekly_tokens == 300


def test_empty_db_is_idle_with_fixed_resets(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    _create_db(db).close()
    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.available
    assert result.is_idle
    assert result.primary_pct == 0.0
    assert result.weekly_pct == 0.0
    assert result.window_kind == "fixed"
    assert result.primary_reset_at == NOW_PRIMARY_RESET
    assert result.weekly_reset_at == NOW_WEEKLY_RESET


def test_fixed_primary_reset_alignment(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 3600) * 1000, _opencode_msg(input_t=100))
    _insert(conn, "m2", (NOW - 60) * 1000, _opencode_msg(input_t=100))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.primary_reset_at == NOW_PRIMARY_RESET
    assert result.primary_reset_at == (NOW // (5 * 3600)) * (5 * 3600) + 5 * 3600


def test_fixed_weekly_reset_alignment(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 60) * 1000, _opencode_msg(input_t=100))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.weekly_reset_at == NOW_WEEKLY_RESET


def test_total_field_preferred_over_components(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 60) * 1000, _opencode_msg(input_t=10, output_t=10, total=999))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.primary_tokens == 999


def test_skips_zero_token_rows(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 60) * 1000, _opencode_msg(input_t=0, output_t=0))
    _insert(conn, "m2", (NOW - 60) * 1000, _opencode_msg(input_t=100))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.primary_tokens == 100


def test_pct_not_clamped_shows_over_limit(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 60) * 1000, _opencode_msg(input_t=99999))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.primary_pct == 9999.9


def test_dataclass_fields():
    u = OpencodeUsage(available=True)
    assert hasattr(u, "primary_pct")
    assert hasattr(u, "weekly_pct")
    assert hasattr(u, "monthly_pct")
    assert hasattr(u, "primary_tokens")
    assert hasattr(u, "weekly_tokens")
    assert hasattr(u, "monthly_tokens")
    assert hasattr(u, "primary_limit_tokens")
    assert hasattr(u, "weekly_limit_tokens")
    assert hasattr(u, "monthly_limit_tokens")
    assert hasattr(u, "is_idle")


def test_monthly_window_excludes_35d_rows(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m5d", (NOW - 5 * 86400) * 1000, _opencode_msg(input_t=100))
    _insert(conn, "m20d", (NOW - 20 * 86400) * 1000, _opencode_msg(input_t=200))
    _insert(conn, "m35d", (NOW - 35 * 86400) * 1000, _opencode_msg(input_t=400))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=100000,
        now=NOW,
    )
    assert result.available
    assert result.monthly_tokens == 300
    assert result.monthly_pct == 0.3


def test_monthly_limit_unset_still_returns_tokens_and_no_error(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 86400) * 1000, _opencode_msg(input_t=500))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=0,
        now=NOW,
    )
    assert result.available
    assert result.monthly_tokens == 500
    assert result.monthly_pct == 0.0
    assert result.monthly_limit_tokens == 0


def test_fixed_monthly_reset_alignment(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 10 * 86400) * 1000, _opencode_msg(input_t=100))
    _insert(conn, "m2", (NOW - 86400) * 1000, _opencode_msg(input_t=100))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=100000,
        now=NOW,
    )
    assert result.monthly_reset_at == NOW_MONTHLY_RESET


def test_monthly_window_empty_still_has_fixed_reset(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "old", (NOW - 31 * 86400) * 1000, _opencode_msg(input_t=999))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=100000,
        now=NOW,
    )
    assert result.available
    assert result.monthly_tokens == 0
    assert result.monthly_reset_at == NOW_MONTHLY_RESET
    assert result.is_idle


def test_is_idle_false_when_primary_has_tokens(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 60) * 1000, _opencode_msg(input_t=100))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        now=NOW,
    )
    assert result.primary_tokens == 100
    assert result.is_idle is False


def test_is_idle_true_when_only_monthly_has_tokens(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    _insert(conn, "m1", (NOW - 10 * 86400) * 1000, _opencode_msg(input_t=500))
    conn.commit()
    conn.close()

    result = fetch_opencode(
        db_path=db,
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=100000,
        now=NOW,
    )
    assert result.primary_tokens == 0
    assert result.weekly_tokens == 0
    assert result.monthly_tokens == 500
    assert result.is_idle is True


def test_zen_and_go_have_identical_fixed_resets(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    for ts_off in (60, 3 * 86400, 10 * 86400):
        _insert(conn, f"z{ts_off}", (NOW - ts_off) * 1000, _opencode_msg(input_t=111, provider="opencode"))
        _insert(conn, f"g{ts_off}", (NOW - ts_off) * 1000, _opencode_msg(input_t=111, provider="opencode-go"))
    conn.commit()
    conn.close()

    zen = fetch_opencode(
        db_path=db,
        provider_id="opencode",
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=100000,
        now=NOW,
    )
    go = fetch_opencode(
        db_path=db,
        provider_id="opencode-go",
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
        monthly_limit_tokens=100000,
        now=NOW,
    )
    assert zen.primary_reset_at == go.primary_reset_at
    assert zen.weekly_reset_at == go.weekly_reset_at
    assert zen.monthly_reset_at == go.monthly_reset_at
    assert (zen.primary_tokens, zen.weekly_tokens, zen.monthly_tokens) == (
        go.primary_tokens,
        go.weekly_tokens,
        go.monthly_tokens,
    )
