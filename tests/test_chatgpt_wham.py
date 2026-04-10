from __future__ import annotations

from unittest.mock import MagicMock, patch

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

    return mock_requests, mock_bc3, import_side_effect


def test_successful_fetch():
    mock_requests, mock_bc3, import_side = _mock_modules()
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
        },
        "code_review_rate_limit": {"used_percent": 10.0, "reset_at": 1700001000},
    }

    session.get.side_effect = [session_resp, wham_resp]

    with patch("importlib.import_module", side_effect=import_side):
        result = fetch_chatgpt("firefox")

    assert result.available
    assert result.primary_pct == 42.5
    assert result.review_pct == 10.0


def test_session_http_error():
    mock_requests, mock_bc3, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    session_resp = MagicMock()
    session_resp.status_code = 403
    session.get.return_value = session_resp

    with patch("importlib.import_module", side_effect=import_side):
        result = fetch_chatgpt()

    assert not result.available
    assert "403" in result.error


def test_no_access_token():
    mock_requests, mock_bc3, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    session_resp = MagicMock()
    session_resp.status_code = 200
    session_resp.json.return_value = {}
    session.get.return_value = session_resp

    with patch("importlib.import_module", side_effect=import_side):
        result = fetch_chatgpt()

    assert not result.available
    assert "access token" in result.error


def test_chatgpt_usage_has_no_codex_fields():
    u = ChatGPTUsage(available=True)
    assert not hasattr(u, "codex_pct")
    assert not hasattr(u, "codex_reset_at")
