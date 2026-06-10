from __future__ import annotations

import importlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from token_usage import _normalize
from token_usage.claude import oauth_usage as oauth_mod
from token_usage.formatters import statusbar, detail, json_out
from token_usage.openai_chat import chatgpt_wham as wham_mod
from token_usage.kimi import usage as kimi_mod
from token_usage.opencode.usage import fetch_opencode


# ---------------------------------------------------------------------------
# ChatGPT schema failures
# ---------------------------------------------------------------------------

def _chatgpt_mock_session(broken_wham_payload: dict):
    mock_requests = MagicMock()
    mock_bc3 = MagicMock()

    def import_side(name, *a, **kw):
        if name == "curl_cffi.requests":
            return mock_requests
        if name == "browser_cookie3":
            return mock_bc3
        return importlib.import_module(name, *a, **kw)

    session = MagicMock()
    mock_requests.Session.return_value = session
    session_resp = MagicMock()
    session_resp.status_code = 200
    session_resp.json.return_value = {"accessToken": "tok"}
    wham_resp = MagicMock()
    wham_resp.status_code = 200
    wham_resp.json.return_value = broken_wham_payload
    session.get.side_effect = [session_resp, wham_resp]
    return mock_requests, import_side


@pytest.mark.parametrize(
    "broken_payload, expected_substring",
    [
        (
            {"rate_limit": {"primary_window": {"reset_at": 4081503240}}},
            "schema: missing primary_window used_percent",
        ),
        (
            {"rate_limit": {}},
            "schema: missing primary_window used_percent",
        ),
        (
            {},
            "schema: missing primary_window used_percent",
        ),
    ],
)
def test_chatgpt_schema_failure_never_zero(broken_payload, expected_substring) -> None:
    mock_requests, import_side = _chatgpt_mock_session(broken_payload)
    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
    ):
        result = wham_mod.fetch_chatgpt()

    assert not result.available
    assert expected_substring in result.error

    data = _normalize.normalize_windows(asdict(result), _normalize.OPENAI_WINDOW_FIELDS)
    sb = statusbar.format_compact({}, data)
    assert sb == "o err", f"statusbar must show 'o err', got {sb!r}"
    assert "0%" not in sb, "statusbar must NEVER show 0% on schema error"

    det = detail.format_detail(None, data)
    assert result.error in det
    assert "unavailable:" in det

    j = json.loads(json_out.format_json({}, data))
    assert j["openai"]["available"] is False
    assert expected_substring in j["openai"]["error"]


# ---------------------------------------------------------------------------
# Kimi schema failures
# ---------------------------------------------------------------------------

def _kimi_mock_session(broken_payload: dict):
    mock_requests = MagicMock()
    mock_bc3 = MagicMock()

    def import_side(name, *a, **kw):
        if name == "curl_cffi.requests":
            return mock_requests
        if name == "browser_cookie3":
            return mock_bc3
        return importlib.import_module(name, *a, **kw)

    session = MagicMock()
    mock_requests.Session.return_value = session
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = broken_payload
    session.post.return_value = resp
    return mock_requests, import_side


def _kimi_auth_jar():
    cookie = MagicMock()
    cookie.name = "kimi-auth"
    cookie.value = "jwt"
    jar = MagicMock()
    jar.__iter__ = lambda self: iter([cookie])
    return jar


@pytest.mark.parametrize(
    "broken_payload, expected_substring",
    [
        # Missing 5h window entirely
        (
            {"usages": [{"scope": "FEATURE_CODING", "detail": {"limit": "100", "remaining": "20"}, "limits": []}]},
            "schema: no 5h window",
        ),
        # Renamed timeUnit → matcher fails
        (
            {
                "usages": [
                    {
                        "scope": "FEATURE_CODING",
                        "detail": {"limit": "100", "remaining": "20"},
                        "limits": [
                            {
                                "window": {"duration": 300, "timeUnit": "TIME_UNIT_HOUR"},
                                "detail": {"limit": "100", "remaining": "75"},
                            }
                        ],
                    }
                ]
            },
            "schema: no 5h window",
        ),
        # Missing limits key
        (
            {"usages": [{"scope": "FEATURE_CODING", "detail": {"limit": "100", "remaining": "20"}}]},
            "schema: no 5h window",
        ),
    ],
)
def test_kimi_schema_failure_never_zero(broken_payload, expected_substring) -> None:
    mock_requests, import_side = _kimi_mock_session(broken_payload)
    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_kimi_auth_jar()),
    ):
        result = kimi_mod.fetch_kimi()

    assert not result.available
    assert expected_substring in result.error

    data = _normalize.normalize_windows(asdict(result), _normalize.KIMI_WINDOW_FIELDS)
    sb = statusbar.format_compact({}, None, data)
    assert sb == "k err", f"statusbar must show 'k err', got {sb!r}"
    assert "0%" not in sb, "statusbar must NEVER show 0% on schema error"

    det = detail.format_detail(None, None, data)
    assert result.error in det
    assert "unavailable:" in det

    j = json.loads(json_out.format_json({}, None, data))
    assert j["kimi"]["available"] is False
    assert expected_substring in j["kimi"]["error"]


# ---------------------------------------------------------------------------
# Claude OAuth schema failures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "broken_usage, expected_substring",
    [
        (
            {"five_hour": {"resets_at": "2026-04-08T02:00:00+00:00"}, "seven_day": {"utilization": 15.0}},
            "schema: missing five_hour utilization",
        ),
        (
            {"five_hour": {"utilization": 72.0}, "seven_day": {"resets_at": "2026-04-13T20:00:00+00:00"}},
            "schema: missing seven_day utilization",
        ),
        (
            {"seven_day": {"utilization": 15.0}},
            "schema: missing five_hour utilization",
        ),
    ],
)
def test_claude_oauth_schema_failure_never_zero(broken_usage, expected_substring) -> None:
    with (
        patch.object(oauth_mod, "_read_token", return_value=("fake-token", None)),
        patch.object(oauth_mod, "_http_get", return_value=(broken_usage, None)),
    ):
        result = oauth_mod.fetch_usage()

    assert not result.available
    assert expected_substring in result.error

    data = _normalize.normalize_windows(asdict(result), _normalize.OPENAI_WINDOW_FIELDS)
    sb = statusbar.format_compact(data)
    assert sb == "c err", f"statusbar must show 'c err', got {sb!r}"
    assert "0%" not in sb, "statusbar must NEVER show 0% on schema error"

    det = detail.format_detail(data)
    assert result.error in det
    assert "unavailable:" in det

    j = json.loads(json_out.format_json(data))
    assert j["claude"]["available"] is False
    assert expected_substring in j["claude"]["error"]


# ---------------------------------------------------------------------------
# OpenCode schema/DB failures
# ---------------------------------------------------------------------------

def test_opencode_missing_db_file() -> None:
    result = fetch_opencode(db_path=Path("/nonexistent/opencode.db"), primary_limit_tokens=1000, weekly_limit_tokens=10000)
    assert not result.available
    assert "not found" in result.error

    data = _normalize.normalize_windows(asdict(result), _normalize.OPENCODE_WINDOW_FIELDS)
    sb = statusbar.format_compact({}, None, None, data)
    assert sb == "e err", f"statusbar must show 'e err', got {sb!r}"
    assert "0%" not in sb

    det = detail.format_detail(None, None, None, data)
    assert result.error in det
    assert "unavailable:" in det

    j = json.loads(json_out.format_json({}, None, None, data))
    assert j["opencode"]["available"] is False


def test_opencode_missing_table(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    # Create empty sqlite file without message table
    sqlite3.connect(db).close()

    result = fetch_opencode(db_path=db, primary_limit_tokens=1000, weekly_limit_tokens=10000)
    assert not result.available
    assert "read failed" in result.error or "open failed" in result.error

    data = _normalize.normalize_windows(asdict(result), _normalize.OPENCODE_WINDOW_FIELDS)
    sb = statusbar.format_compact({}, None, None, data)
    assert sb == "e err", f"statusbar must show 'e err', got {sb!r}"
    assert "0%" not in sb

    det = detail.format_detail(None, None, None, data)
    assert result.error in det

    j = json.loads(json_out.format_json({}, None, None, data))
    assert j["opencode"]["available"] is False


def test_opencode_corrupt_db_file(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    db.write_text("this is not sqlite")

    result = fetch_opencode(db_path=db, primary_limit_tokens=1000, weekly_limit_tokens=10000)
    assert not result.available
    assert "open failed" in result.error or "read failed" in result.error or "not a database" in result.error

    data = _normalize.normalize_windows(asdict(result), _normalize.OPENCODE_WINDOW_FIELDS)
    sb = statusbar.format_compact({}, None, None, data)
    assert sb == "e err", f"statusbar must show 'e err', got {sb!r}"
    assert "0%" not in sb

    det = detail.format_detail(None, None, None, data)
    assert result.error in det

    j = json.loads(json_out.format_json({}, None, None, data))
    assert j["opencode"]["available"] is False


# ---------------------------------------------------------------------------
# OpenCode-Go schema/DB failures
# ---------------------------------------------------------------------------

def test_opencode_go_missing_db_file() -> None:
    result = fetch_opencode(
        provider_id="opencode-go",
        db_path=Path("/nonexistent/opencode.db"),
        primary_limit_tokens=1000,
        weekly_limit_tokens=10000,
    )
    assert not result.available
    assert "not found" in result.error

    data = _normalize.normalize_windows(asdict(result), _normalize.OPENCODE_WINDOW_FIELDS)
    sb = statusbar.format_compact({}, None, None, None, data)
    assert sb == "g err", f"statusbar must show 'g err', got {sb!r}"
    assert "0%" not in sb

    det = detail.format_detail(None, None, None, None, data)
    assert result.error in det
    assert "unavailable:" in det

    j = json.loads(json_out.format_json({}, None, None, None, data))
    assert j["opencode_go"]["available"] is False
