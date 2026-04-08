from __future__ import annotations

import importlib
from unittest.mock import patch

oauth_usage = importlib.import_module("token_usage.claude.oauth_usage")

SAMPLE_USAGE = {
    "five_hour": {"utilization": 72.0, "resets_at": "2026-04-08T02:00:00+00:00"},
    "seven_day": {"utilization": 15.0, "resets_at": "2026-04-13T20:00:00+00:00"},
    "seven_day_oauth_apps": None,
    "seven_day_opus": None,
    "seven_day_sonnet": {"utilization": 0.0, "resets_at": None},
    "seven_day_cowork": None,
    "iguana_necktie": None,
    "extra_usage": {"is_enabled": False, "monthly_limit": None, "used_credits": None, "utilization": None},
}

SAMPLE_PROFILE = {
    "account": {"email": "test@example.com", "has_claude_max": True, "has_claude_pro": False},
    "organization": {"organization_type": "claude_max", "rate_limit_tier": "default_claude_max_5x"},
}


def test_parse_usage_response() -> None:
    with patch.object(oauth_usage, "_read_token", return_value=("fake-token", None)):
        def fake_get(url, token, timeout=10):
            if "profile" in url:
                return SAMPLE_PROFILE, None, None
            if "usage" in url:
                return SAMPLE_USAGE, None, None
            return None, "unknown url", None

        with patch.object(oauth_usage, "_http_get", side_effect=fake_get):
            result = oauth_usage.fetch_usage()

    assert result.available is True
    assert result.error is None
    assert result.retry_after_seconds is None
    assert result.five_hour_pct == 72.0
    assert result.seven_day_pct == 15.0
    assert result.seven_day_sonnet_pct == 0.0
    assert result.seven_day_opus_pct is None
    assert result.subscription_type == "claude_max"
    assert result.rate_limit_tier == "default_claude_max_5x"
    assert result.five_hour_resets_at is not None
    assert result.five_hour_resets_at.year == 2026
    assert result.five_hour_resets_at.month == 4


def test_missing_credentials() -> None:
    with patch.object(oauth_usage, "_read_token", return_value=(None, "credentials file not found")):
        result = oauth_usage.fetch_usage()
    assert result.available is False
    assert "not found" in result.error


def test_http_error() -> None:
    with patch.object(oauth_usage, "_read_token", return_value=("fake-token", None)):
        def fake_get(url, token, timeout=10):
            return None, "http 401: unauthorized", None

        with patch.object(oauth_usage, "_http_get", side_effect=fake_get):
            result = oauth_usage.fetch_usage()
    assert result.available is False
    assert "401" in result.error
    assert result.retry_after_seconds is None


def test_rate_limit_propagates_retry_after() -> None:
    with patch.object(oauth_usage, "_read_token", return_value=("fake-token", None)):
        def fake_get(url, token, timeout=10):
            if "profile" in url:
                return SAMPLE_PROFILE, None, None
            return None, "http 429: rate limited", 272

        with patch.object(oauth_usage, "_http_get", side_effect=fake_get):
            result = oauth_usage.fetch_usage()

    assert result.available is False
    assert "429" in result.error
    assert result.retry_after_seconds == 272
    assert result.subscription_type == "claude_max"
