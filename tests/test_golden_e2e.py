from __future__ import annotations

import importlib
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from token_usage import cli as cli_mod
from token_usage import cache as cache_mod
from token_usage import config as config_mod
from token_usage import _normalize
from token_usage.claude import oauth_usage as oauth_mod
from token_usage.claude import statusline as statusline_mod
from token_usage.claude import local_summary as local_summary_mod
from token_usage.claude.models import ClaudeUsage
from token_usage.openai_chat import chatgpt_wham as wham_mod
from token_usage.kimi import usage as kimi_mod


def _local_hhmm(epoch: int) -> str:
    """Mirror of statusbar._local_hhmm for deterministic expectations."""
    try:
        return datetime.fromtimestamp(epoch).astimezone().strftime("%H:%M")
    except (ValueError, OSError):
        return ""


# ---------------------------------------------------------------------------
# ChatGPT HTTP mock helpers
# ---------------------------------------------------------------------------

def _mock_chatgpt_modules():
    mock_requests = MagicMock()
    mock_bc3 = MagicMock()

    def import_side(name, *a, **kw):
        if name == "curl_cffi.requests":
            return mock_requests
        if name == "browser_cookie3":
            return mock_bc3
        return importlib.import_module(name, *a, **kw)

    return mock_requests, import_side


def _chatgpt_session_resp(token: str = "tok123"):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"accessToken": token}
    return m


def _chatgpt_wham_resp(
    *,
    primary_used: float = 42.5,
    primary_reset: int = 4_081_503_240,
    weekly_used: float = 80.0,
    weekly_reset: int = 4_082_100_040,
    review_used: float = 10.0,
    review_reset: int = 4_081_504_240,
):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {
        "rate_limit": {
            "primary_window": {"used_percent": primary_used, "reset_at": primary_reset},
            "secondary_window": {"used_percent": weekly_used, "reset_at": weekly_reset},
        },
        "code_review_rate_limit": {"used_percent": review_used, "reset_at": review_reset},
    }
    return m


# ---------------------------------------------------------------------------
# Kimi HTTP mock helpers
# ---------------------------------------------------------------------------

def _mock_kimi_modules():
    mock_requests = MagicMock()
    mock_bc3 = MagicMock()

    def import_side(name, *a, **kw):
        if name == "curl_cffi.requests":
            return mock_requests
        if name == "browser_cookie3":
            return mock_bc3
        return importlib.import_module(name, *a, **kw)

    return mock_requests, import_side


def _kimi_auth_jar(token: str = "kimi-jwt"):
    cookie = MagicMock()
    cookie.name = "kimi-auth"
    cookie.value = token
    jar = MagicMock()
    jar.__iter__ = lambda self: iter([cookie])
    return jar


def _kimi_usage_resp(
    *,
    five_hour_limit: str = "100",
    five_hour_remaining: str = "75",
    five_hour_reset: str = "2099-04-26T19:54:00Z",
    weekly_limit: str = "100",
    weekly_remaining: str = "20",
    weekly_reset: str = "2099-05-03T14:54:00Z",
):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {
        "usages": [
            {
                "scope": "FEATURE_CODING",
                "detail": {
                    "limit": weekly_limit,
                    "remaining": weekly_remaining,
                    "resetTime": weekly_reset,
                },
                "limits": [
                    {
                        "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {
                            "limit": five_hour_limit,
                            "remaining": five_hour_remaining,
                            "resetTime": five_hour_reset,
                        },
                    }
                ],
            }
        ]
    }
    return m


# ---------------------------------------------------------------------------
# OpenCode SQLite helpers
# ---------------------------------------------------------------------------

NOW = 1_777_400_000


def _create_opencode_db(path: Path) -> sqlite3.Connection:
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


def _opencode_msg(input_t: int = 0, output_t: int = 0, total: int | None = None, provider: str = "opencode") -> dict:
    tokens: dict = {"input": input_t, "output": output_t, "cache": {"read": 0, "write": 0}}
    if total is not None:
        tokens["total"] = total
    return {"role": "assistant", "providerID": provider, "modelID": "claude-sonnet-4-6", "tokens": tokens}


# ---------------------------------------------------------------------------
# 1. Claude OAuth golden
# ---------------------------------------------------------------------------


def test_claude_oauth_golden_statusbar(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    reset_5h = datetime(2099, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
    reset_7d = datetime(2099, 4, 13, 20, 0, 0, tzinfo=timezone.utc)
    oauth_result = ClaudeUsage(
        available=True,
        five_hour_pct=42.0,
        five_hour_resets_at=reset_5h,
        seven_day_pct=15.0,
        seven_day_resets_at=reset_7d,
        subscription_type="claude-max",
        rate_limit_tier="oauth",
    )
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=None),
        patch.object(oauth_mod, "fetch_usage", return_value=oauth_result),
        patch.object(local_summary_mod, "compute_local", return_value=(ClaudeUsage(available=False, error="none"), {})),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "claude"])
    assert rc == 0
    out = capsys.readouterr().out
    # 5h pct (42) > 7d pct (15) → 5h drives
    expected = f"c42%@{_local_hhmm(int(reset_5h.timestamp()))}"
    assert out == expected


def test_claude_oauth_golden_detail(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    reset_5h = datetime(2099, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
    reset_7d = datetime(2099, 4, 13, 20, 0, 0, tzinfo=timezone.utc)
    oauth_result = ClaudeUsage(
        available=True,
        five_hour_pct=42.0,
        five_hour_resets_at=reset_5h,
        seven_day_pct=15.0,
        seven_day_resets_at=reset_7d,
        subscription_type="claude-max",
        rate_limit_tier="oauth",
    )
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=None),
        patch.object(oauth_mod, "fetch_usage", return_value=oauth_result),
        patch.object(local_summary_mod, "compute_local", return_value=(ClaudeUsage(available=False, error="none"), {})),
    ):
        rc = cli_mod.main(["--detail", "--only", "claude"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Claude" in out
    assert "42.0%" in out
    assert "15.0%" in out
    assert "source: oauth" in out
    assert "← bar" in out


# ---------------------------------------------------------------------------
# 2. Claude Statusline golden
# ---------------------------------------------------------------------------


def test_claude_statusline_golden_statusbar(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    reset_5h = datetime(2099, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
    reset_7d = datetime(2099, 4, 13, 20, 0, 0, tzinfo=timezone.utc)
    sl_result = ClaudeUsage(
        available=True,
        five_hour_pct=55.0,
        five_hour_resets_at=reset_5h,
        seven_day_pct=14.0,
        seven_day_resets_at=reset_7d,
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=sl_result),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time()),
        patch.object(oauth_mod, "fetch_usage"),
        patch.object(local_summary_mod, "compute_local", return_value=(ClaudeUsage(available=False, error="none"), {})),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "claude"])
    assert rc == 0
    out = capsys.readouterr().out
    expected = f"c55%@{_local_hhmm(int(reset_5h.timestamp()))}"
    assert out == expected


def test_claude_statusline_golden_detail(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    reset_5h = datetime(2099, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
    reset_7d = datetime(2099, 4, 13, 20, 0, 0, tzinfo=timezone.utc)
    sl_result = ClaudeUsage(
        available=True,
        five_hour_pct=55.0,
        five_hour_resets_at=reset_5h,
        seven_day_pct=14.0,
        seven_day_resets_at=reset_7d,
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=sl_result),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time()),
        patch.object(oauth_mod, "fetch_usage"),
        patch.object(local_summary_mod, "compute_local", return_value=(ClaudeUsage(available=False, error="none"), {})),
    ):
        rc = cli_mod.main(["--detail", "--only", "claude"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Claude" in out
    assert "55.0%" in out
    assert "14.0%" in out
    assert "source: statusline" in out
    assert "← bar" in out


# ---------------------------------------------------------------------------
# 3. ChatGPT golden
# ---------------------------------------------------------------------------


def test_chatgpt_golden_statusbar(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.openai_enabled = True
    mock_requests, import_side = _mock_chatgpt_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    session.get.side_effect = [
        _chatgpt_session_resp(),
        _chatgpt_wham_resp(primary_used=42.5, weekly_used=80.0),
    ]
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch("importlib.import_module", side_effect=import_side),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "chatgpt"])
    assert rc == 0
    out = capsys.readouterr().out
    # weekly (80) > primary (42.5) → weekly drives
    expected = f"o80%@{_local_hhmm(4_082_100_040)}"
    assert out == expected


def test_chatgpt_golden_detail(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.openai_enabled = True
    mock_requests, import_side = _mock_chatgpt_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    session.get.side_effect = [
        _chatgpt_session_resp(),
        _chatgpt_wham_resp(primary_used=42.5, weekly_used=80.0),
    ]
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch("importlib.import_module", side_effect=import_side),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
    ):
        rc = cli_mod.main(["--detail", "--only", "chatgpt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ChatGPT Plus" in out
    assert "42.5%" in out
    assert "80.0%" in out
    assert "← bar" in out


# ---------------------------------------------------------------------------
# 4. Kimi golden
# ---------------------------------------------------------------------------


def test_kimi_golden_statusbar(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.kimi_enabled = True
    mock_requests, import_side = _mock_kimi_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    session.post.return_value = _kimi_usage_resp(
        five_hour_limit="100",
        five_hour_remaining="75",
        five_hour_reset="2099-04-26T19:54:00Z",
        weekly_limit="100",
        weekly_remaining="20",
        weekly_reset="2099-05-03T14:54:00Z",
    )
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_kimi_auth_jar()),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "kimi"])
    assert rc == 0
    out = capsys.readouterr().out
    # weekly=80%, primary=25% → weekly drives
    expected = f"k80%@{_local_hhmm(4081503240)}"
    assert out == expected


def test_kimi_golden_detail(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.kimi_enabled = True
    mock_requests, import_side = _mock_kimi_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    session.post.return_value = _kimi_usage_resp(
        five_hour_limit="100",
        five_hour_remaining="75",
        five_hour_reset="2099-04-26T19:54:00Z",
        weekly_limit="100",
        weekly_remaining="20",
        weekly_reset="2099-05-03T14:54:00Z",
    )
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_kimi_auth_jar()),
    ):
        rc = cli_mod.main(["--detail", "--only", "kimi"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Kimi Code" in out
    assert "25.0%" in out
    assert "80.0%" in out
    assert "← bar" in out


# ---------------------------------------------------------------------------
# 5. OpenCode golden
# ---------------------------------------------------------------------------


def test_opencode_golden_statusbar(capsys, tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_opencode_db(db)
    ts_ms = (NOW - 100) * 1000
    _insert_opencode(conn, "m1", ts_ms, _opencode_msg(input_t=500, provider="opencode"))
    conn.commit()
    conn.close()

    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.opencode_enabled = True
    cfg.opencode_db_path = str(db)
    cfg.opencode_primary_limit_tokens = 1000
    cfg.opencode_weekly_limit_tokens = 10000

    monkeypatch.setattr(time, "time", lambda: NOW)

    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "opencode"])
    assert rc == 0
    out = capsys.readouterr().out
    # primary=50%, weekly=5% → primary drives
    primary_reset = NOW + 5 * 3600 - 100  # oldest + window
    expected = f"e50%~{_local_hhmm(primary_reset)}"
    assert out == expected


def test_opencode_golden_detail(capsys, tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_opencode_db(db)
    ts_ms = (NOW - 100) * 1000
    _insert_opencode(conn, "m1", ts_ms, _opencode_msg(input_t=500, provider="opencode"))
    conn.commit()
    conn.close()

    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.opencode_enabled = True
    cfg.opencode_db_path = str(db)
    cfg.opencode_primary_limit_tokens = 1000
    cfg.opencode_weekly_limit_tokens = 10000

    monkeypatch.setattr(time, "time", lambda: NOW)

    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
    ):
        rc = cli_mod.main(["--detail", "--only", "opencode"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OpenCode" in out
    assert "50.0%" in out
    assert "5.0%" in out
    assert "(rolling)" in out
    assert "← bar" in out
    assert "500 / 1,000" in out


# ---------------------------------------------------------------------------
# 6. OpenCode-Go golden
# ---------------------------------------------------------------------------


def test_opencode_go_golden_statusbar(capsys, tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_opencode_db(db)
    ts_ms = (NOW - 100) * 1000
    _insert_opencode(conn, "m1", ts_ms, _opencode_msg(input_t=700, provider="opencode-go"))
    conn.commit()
    conn.close()

    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.opencode_go_enabled = True
    cfg.opencode_go_db_path = str(db)
    cfg.opencode_go_primary_limit_tokens = 1000
    cfg.opencode_go_weekly_limit_tokens = 10000

    monkeypatch.setattr(time, "time", lambda: NOW)

    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "opencode-go"])
    assert rc == 0
    out = capsys.readouterr().out
    primary_reset = NOW + 5 * 3600 - 100
    expected = f"g70%~{_local_hhmm(primary_reset)}"
    assert out == expected


def test_opencode_go_golden_detail(capsys, tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_opencode_db(db)
    ts_ms = (NOW - 100) * 1000
    _insert_opencode(conn, "m1", ts_ms, _opencode_msg(input_t=700, provider="opencode-go"))
    conn.commit()
    conn.close()

    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.opencode_go_enabled = True
    cfg.opencode_go_db_path = str(db)
    cfg.opencode_go_primary_limit_tokens = 1000
    cfg.opencode_go_weekly_limit_tokens = 10000

    monkeypatch.setattr(time, "time", lambda: NOW)

    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
    ):
        rc = cli_mod.main(["--detail", "--only", "opencode-go"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OpenCode Go" in out
    assert "70.0%" in out
    assert "(rolling)" in out
    assert "← bar" in out
    assert "700 / 1,000" in out


# ---------------------------------------------------------------------------
# 7. Combined multi-provider golden
# ---------------------------------------------------------------------------


def test_combined_claude_chatgpt_kimi_statusbar(capsys) -> None:
    cfg = config_mod.Config()
    cfg.cache_ttl_seconds = 0
    cfg.openai_enabled = True
    cfg.kimi_enabled = True

    reset_5h = datetime(2099, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
    reset_7d = datetime(2099, 4, 13, 20, 0, 0, tzinfo=timezone.utc)
    claude_result = ClaudeUsage(
        available=True,
        five_hour_pct=30.0,
        five_hour_resets_at=reset_5h,
        seven_day_pct=50.0,
        seven_day_resets_at=reset_7d,
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )

    mock_requests_chatgpt, import_side_chatgpt = _mock_chatgpt_modules()
    session_chatgpt = MagicMock()
    mock_requests_chatgpt.Session.return_value = session_chatgpt
    session_chatgpt.get.side_effect = [
        _chatgpt_session_resp(),
        _chatgpt_wham_resp(primary_used=10.0, primary_reset=4_081_503_240, weekly_used=90.0, weekly_reset=4_082_100_040),
    ]

    mock_requests_kimi, import_side_kimi = _mock_kimi_modules()
    session_kimi = MagicMock()
    mock_requests_kimi.Session.return_value = session_kimi
    session_kimi.post.return_value = _kimi_usage_resp(
        five_hour_limit="100",
        five_hour_remaining="90",
        five_hour_reset="2099-04-26T19:54:00Z",
        weekly_limit="100",
        weekly_remaining="50",
        weekly_reset="2099-05-03T14:54:00Z",
    )

    def _combined_import_side(name, *a, **kw):
        if name == "curl_cffi.requests":
            # Return a new mock each time; but we need separate sessions.
            # Since _fetch_openai and _fetch_kimi each create their own Session,
            # and they're called sequentially, we can use a counter.
            return mock_requests_chatgpt if _combined_import_side._counter == 0 else mock_requests_kimi
        if name == "browser_cookie3":
            return MagicMock()
        return importlib.import_module(name, *a, **kw)

    _combined_import_side._counter = 0
    original_session = mock_requests_chatgpt.Session

    def _chatgpt_session_factory(*a, **kw):
        _combined_import_side._counter += 1
        return original_session(*a, **kw)

    mock_requests_chatgpt.Session = _chatgpt_session_factory

    # Actually, simpler: patch both modules' importlib separately
    with (
        patch.object(config_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(statusline_mod, "read_statusline_usage", return_value=claude_result),
        patch.object(cli_mod, "_statusline_mtime", return_value=time.time()),
        patch.object(oauth_mod, "fetch_usage"),
        patch.object(local_summary_mod, "compute_local", return_value=(ClaudeUsage(available=False, error="none"), {})),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
        patch.object(kimi_mod, "load_cookies", return_value=_kimi_auth_jar()),
    ):
        # We need to patch importlib for both chatgpt and kimi
        # Since they import inside their fetch functions, patching globally works.
        call_count = [0]

        def _global_import_side(name, *a, **kw):
            if name == "curl_cffi.requests":
                call_count[0] += 1
                return mock_requests_chatgpt if call_count[0] <= 1 else mock_requests_kimi
            if name == "browser_cookie3":
                return MagicMock()
            return importlib.import_module(name, *a, **kw)

        with patch("importlib.import_module", side_effect=_global_import_side):
            rc = cli_mod.main(["--statusbar", "--only", "claude,chatgpt,kimi"])

    assert rc == 0
    out = capsys.readouterr().out
    # claude: 7d=50 > 5h=30 → c50%
    # chatgpt: weekly=90 > primary=10 → o90%
    # kimi: weekly=50 > primary=10 → k50%
    c_reset = _local_hhmm(int(reset_7d.timestamp()))
    o_reset = _local_hhmm(4_082_100_040)
    k_reset = _local_hhmm(4081503240)
    assert out == f"c50%@{c_reset} o90%@{o_reset} k50%@{k_reset}"
