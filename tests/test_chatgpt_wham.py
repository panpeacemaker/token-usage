from __future__ import annotations

from unittest.mock import MagicMock, patch

from token_usage.openai_chat import chatgpt_wham as wham_mod
from token_usage.openai_chat.chatgpt_wham import ChatGPTUsage, fetch_chatgpt


def test_missing_curl_cffi():
    with patch("importlib.import_module", side_effect=ImportError("no curl_cffi")):
        result = fetch_chatgpt()
    assert not result.available
    assert "curl_cffi" in result.error


def test_missing_browser_cookie3():
    fake_requests = MagicMock()

    def import_side_effect(name, *a, **kw):
        if name == "curl_cffi.requests":
            return fake_requests
        raise ImportError("no browser_cookie3")

    with patch("importlib.import_module", side_effect=import_side_effect):
        result = fetch_chatgpt()
    assert not result.available
    assert "browser_cookie3" in result.error


def _mock_modules():
    mock_requests = MagicMock()
    mock_bc3 = MagicMock()

    def import_side_effect(name, *a, **kw):
        if name == "curl_cffi.requests":
            return mock_requests
        if name == "browser_cookie3":
            return mock_bc3
        raise ImportError(name)

    return mock_requests, import_side_effect


def test_successful_fetch():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    session_resp = MagicMock()
    session_resp.status_code = 200
    session_resp.json.return_value = {"accessToken": "tok123"}

    wham_resp = MagicMock()
    wham_resp.status_code = 200
    wham_resp.json.return_value = {
        "rate_limit": {
            "primary_window": {"used_percent": 42.5, "reset_at": 1700000000},
            "secondary_window": {"used_percent": 80.0, "reset_at": 1700604800},
        },
        "code_review_rate_limit": {"used_percent": 10.0, "reset_at": 1700001000},
    }

    session.get.side_effect = [session_resp, wham_resp]

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
    ):
        result = fetch_chatgpt("firefox")

    assert result.available
    assert result.primary_pct == 42.5
    assert result.primary_reset_at == 1700000000
    assert result.weekly_pct == 80.0
    assert result.weekly_reset_at == 1700604800
    assert result.review_pct == 10.0


def test_secondary_window_missing_keeps_weekly_zero():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    session_resp = MagicMock()
    session_resp.status_code = 200
    session_resp.json.return_value = {"accessToken": "tok"}

    wham_resp = MagicMock()
    wham_resp.status_code = 200
    wham_resp.json.return_value = {
        "rate_limit": {"primary_window": {"used_percent": 5.0, "reset_at": 1700000000}},
        "code_review_rate_limit": None,
    }

    session.get.side_effect = [session_resp, wham_resp]

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
    ):
        result = fetch_chatgpt()

    assert result.available
    assert result.weekly_pct == 0.0
    assert result.weekly_reset_at is None
    assert result.review_pct == 0.0


def test_session_http_error():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    session_resp = MagicMock()
    session_resp.status_code = 403
    session.get.return_value = session_resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
    ):
        result = fetch_chatgpt()

    assert not result.available
    assert "403" in result.error


def test_no_access_token():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    session_resp = MagicMock()
    session_resp.status_code = 200
    session_resp.json.return_value = {}
    session.get.return_value = session_resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
    ):
        result = fetch_chatgpt()

    assert not result.available
    assert "access token" in result.error


def test_cookie_discovery_failure_propagates():
    _, import_side = _mock_modules()

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(
            wham_mod,
            "load_cookies",
            side_effect=FileNotFoundError("no zen profile contains cookies for chatgpt.com"),
        ),
    ):
        result = fetch_chatgpt("zen")

    assert not result.available
    assert "no zen profile" in result.error


def test_chatgpt_usage_has_no_codex_fields():
    u = ChatGPTUsage(available=True)
    assert not hasattr(u, "codex_pct")
    assert not hasattr(u, "codex_reset_at")


def test_unknown_browser_propagates_valueerror():
    _, import_side = _mock_modules()
    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(
            wham_mod,
            "load_cookies",
            side_effect=ValueError("unknown browser: phantom"),
        ),
    ):
        result = fetch_chatgpt("phantom")

    assert not result.available
    assert "unknown browser" in result.error


def test_missing_primary_window_used_percent_returns_schema_error():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    session_resp = MagicMock()
    session_resp.status_code = 200
    session_resp.json.return_value = {"accessToken": "tok"}

    wham_resp = MagicMock()
    wham_resp.status_code = 200
    wham_resp.json.return_value = {
        "rate_limit": {"primary_window": {"reset_at": 1700000000}},
    }

    session.get.side_effect = [session_resp, wham_resp]

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(wham_mod, "load_cookies", return_value=MagicMock()),
    ):
        result = fetch_chatgpt()

    assert not result.available
    assert "schema: missing primary_window used_percent" in result.error
