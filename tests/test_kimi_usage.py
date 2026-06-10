from __future__ import annotations

from unittest.mock import MagicMock, patch

from token_usage.kimi import usage as kimi_mod
from token_usage.kimi.usage import KimiUsage, fetch_kimi


def test_missing_curl_cffi():
    with patch("importlib.import_module", side_effect=ImportError("no curl_cffi")):
        result = fetch_kimi()
    assert not result.available
    assert "curl_cffi" in result.error


def test_missing_browser_cookie3():
    fake_requests = MagicMock()

    def import_side_effect(name, *a, **kw):
        if name == "curl_cffi.requests":
            return fake_requests
        raise ImportError("no browser_cookie3")

    with patch("importlib.import_module", side_effect=import_side_effect):
        result = fetch_kimi()
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


def _jar_with_auth(token: str = "kimi-jwt"):
    cookie = MagicMock()
    cookie.name = "kimi-auth"
    cookie.value = token
    jar = MagicMock()
    jar.__iter__ = lambda self: iter([cookie])
    return jar


def test_successful_fetch_parses_weekly_and_five_hour():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "usages": [
            {
                "scope": "FEATURE_CODING",
                "detail": {"limit": "100", "remaining": "20", "resetTime": "2099-05-03T14:54:00Z"},
                "limits": [
                    {
                        "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {
                            "limit": "100",
                            "remaining": "75",
                            "resetTime": "2099-04-26T19:54:00Z",
                        },
                    }
                ],
            }
        ]
    }
    session.post.return_value = resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_jar_with_auth()),
    ):
        result = fetch_kimi("zen")

    assert result.available
    assert result.weekly_pct == 80.0
    assert result.weekly_reset_at == 4081503240
    assert result.primary_pct == 25.0
    assert result.primary_reset_at == 4080916440


def test_expired_window_rolls_to_zero():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "usages": [
            {
                "scope": "FEATURE_CODING",
                "detail": {"limit": "100", "remaining": "20", "resetTime": "2099-05-03T14:54:00Z"},
                "limits": [
                    {
                        "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {
                            "limit": "100",
                            "remaining": "75",
                            "resetTime": "2000-04-26T19:54:00Z",
                        },
                    }
                ],
            }
        ]
    }
    session.post.return_value = resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_jar_with_auth()),
    ):
        result = fetch_kimi("zen")

    assert result.available
    assert result.weekly_pct == 80.0
    assert result.primary_pct == 0.0
    assert result.primary_reset_at is None


def test_fetch_returns_error_when_no_auth_cookie():
    _, import_side = _mock_modules()
    empty_jar = MagicMock()
    empty_jar.__iter__ = lambda self: iter([])

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=empty_jar),
    ):
        result = fetch_kimi("zen")

    assert not result.available
    assert "kimi-auth" in result.error


def test_fetch_returns_error_on_http_failure():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    resp = MagicMock()
    resp.status_code = 401
    session.post.return_value = resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_jar_with_auth()),
    ):
        result = fetch_kimi()

    assert not result.available
    assert "401" in result.error


def test_fetch_returns_error_when_scope_missing():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"usages": [{"scope": "FEATURE_OTHER", "detail": {}}]}
    session.post.return_value = resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_jar_with_auth()),
    ):
        result = fetch_kimi()

    assert not result.available
    assert "FEATURE_CODING" in result.error


def test_zero_limit_yields_zero_pct():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "usages": [
            {
                "scope": "FEATURE_CODING",
                "detail": {"limit": "0", "remaining": "0"},
                "limits": [
                    {
                        "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {"limit": "0", "remaining": "0"},
                    }
                ],
            }
        ]
    }
    session.post.return_value = resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_jar_with_auth()),
    ):
        result = fetch_kimi()

    assert result.available
    assert result.weekly_pct == 0.0
    assert result.primary_pct == 0.0


def test_missing_five_hour_window_returns_schema_error():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "usages": [
            {
                "scope": "FEATURE_CODING",
                "detail": {"limit": "100", "remaining": "20"},
                "limits": [],
            }
        ]
    }
    session.post.return_value = resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_jar_with_auth()),
    ):
        result = fetch_kimi()

    assert not result.available
    assert "schema: no 5h window" in result.error


def test_renamed_window_fields_return_schema_error():
    mock_requests, import_side = _mock_modules()
    session = MagicMock()
    mock_requests.Session.return_value = session
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
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
    }
    session.post.return_value = resp

    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(kimi_mod, "load_cookies", return_value=_jar_with_auth()),
    ):
        result = fetch_kimi()

    assert not result.available
    assert "schema: no 5h window" in result.error


def test_cookie_discovery_failure_propagates():
    _, import_side = _mock_modules()
    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(
            kimi_mod,
            "load_cookies",
            side_effect=FileNotFoundError("no zen profile contains cookies for kimi.com"),
        ),
    ):
        result = fetch_kimi("zen")

    assert not result.available
    assert "no zen profile" in result.error


def test_kimi_usage_dataclass_fields():
    u = KimiUsage(available=True)
    assert hasattr(u, "primary_pct")
    assert hasattr(u, "weekly_pct")
    assert hasattr(u, "primary_reset_at")
    assert hasattr(u, "weekly_reset_at")


def test_unknown_browser_propagates_valueerror():
    _, import_side = _mock_modules()
    with (
        patch("importlib.import_module", side_effect=import_side),
        patch.object(
            kimi_mod,
            "load_cookies",
            side_effect=ValueError("unknown browser: phantom"),
        ),
    ):
        result = fetch_kimi("phantom")

    assert not result.available
    assert "unknown browser" in result.error


def test_reset_epoch_int_seconds():
    assert kimi_mod._reset_epoch({"resetTime": 1777820040}) == 1777820040


def test_reset_epoch_int_milliseconds():
    assert kimi_mod._reset_epoch({"resetTime": 1777820040000}) == 1777820040


def test_reset_epoch_float_seconds():
    assert kimi_mod._reset_epoch({"resetTime": 1777820040.5}) == 1777820040


def test_reset_epoch_string_iso():
    assert kimi_mod._reset_epoch({"resetTime": "2099-05-03T14:54:00Z"}) == 4081503240
