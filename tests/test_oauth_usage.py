from __future__ import annotations

from unittest.mock import patch

from token_usage.claude import oauth_usage

SAMPLE_USAGE = {
    "five_hour": {"utilization": 72.0, "resets_at": "2026-04-08T02:00:00+00:00"},
    "seven_day": {"utilization": 15.0, "resets_at": "2026-04-13T20:00:00+00:00"},
    "seven_day_oauth_apps": None,
    "seven_day_opus": None,
    "seven_day_sonnet": {"utilization": 0.0, "resets_at": None},
    "seven_day_cowork": None,
    "extra_usage": {"is_enabled": False, "monthly_limit": None, "used_credits": None, "utilization": None},
}


def test_parse_usage_response() -> None:
    with patch.object(oauth_usage, "_read_token", return_value=("fake-token", None)), \
         patch.object(oauth_usage, "_http_get", return_value=(SAMPLE_USAGE, None)):
        result = oauth_usage.fetch_usage()

    assert result.available is True
    assert result.error is None
    assert result.five_hour_pct == 72.0
    assert result.seven_day_pct == 15.0
    assert result.seven_day_sonnet_pct == 0.0
    assert result.seven_day_opus_pct is None
    assert result.subscription_type == "claude-max"
    assert result.rate_limit_tier == "oauth"
    assert result.five_hour_resets_at is not None
    assert result.five_hour_resets_at.year == 2026
    assert result.five_hour_resets_at.month == 4


def test_missing_credentials() -> None:
    with patch.object(oauth_usage, "_read_token", return_value=(None, "no OAuth token in any source")):
        result = oauth_usage.fetch_usage()
    assert result.available is False
    assert "no OAuth token" in result.error


def test_http_error_propagates() -> None:
    with patch.object(oauth_usage, "_read_token", return_value=("fake-token", None)), \
         patch.object(oauth_usage, "_http_get", return_value=(None, "http 401: unauthorized")):
        result = oauth_usage.fetch_usage()
    assert result.available is False
    assert "401" in result.error


def test_rate_limit_returns_unavailable() -> None:
    with patch.object(oauth_usage, "_read_token", return_value=("fake-token", None)), \
         patch.object(oauth_usage, "_http_get", return_value=(None, "http 429: Too Many Requests")):
        result = oauth_usage.fetch_usage()
    assert result.available is False
    assert "429" in result.error


def test_opencode_fallback_used_when_claude_missing(tmp_path) -> None:
    claude_file = tmp_path / "claude-creds.json"
    opencode_file = tmp_path / "opencode-auth.json"
    opencode_file.parent.mkdir(parents=True, exist_ok=True)
    opencode_file.write_text('{"anthropic": {"type": "oauth", "access": "sk-opencode"}}')

    with patch.object(oauth_usage, "CREDENTIALS_FILE", claude_file), \
         patch.object(oauth_usage, "OPENCODE_AUTH_FILE", opencode_file):
        token, err = oauth_usage._read_token()
    assert token == "sk-opencode"
    assert err is None


def test_claude_credentials_preferred_when_both_exist(tmp_path) -> None:
    claude_file = tmp_path / "claude-creds.json"
    opencode_file = tmp_path / "opencode-auth.json"
    claude_file.write_text('{"claudeAiOauth": {"accessToken": "sk-claude"}}')
    opencode_file.write_text('{"anthropic": {"type": "oauth", "access": "sk-opencode"}}')

    with patch.object(oauth_usage, "CREDENTIALS_FILE", claude_file), \
         patch.object(oauth_usage, "OPENCODE_AUTH_FILE", opencode_file):
        token, err = oauth_usage._read_token()
    assert token == "sk-claude"
    assert err is None


def test_no_tokens_anywhere(tmp_path) -> None:
    claude_file = tmp_path / "missing-claude.json"
    opencode_file = tmp_path / "missing-opencode.json"
    with patch.object(oauth_usage, "CREDENTIALS_FILE", claude_file), \
         patch.object(oauth_usage, "OPENCODE_AUTH_FILE", opencode_file):
        token, err = oauth_usage._read_token()
    assert token is None
    assert "no OAuth token" in err
