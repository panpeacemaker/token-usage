from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from token_usage.claude import statusline


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_returns_none_when_file_missing(tmp_path: Path) -> None:
    assert statusline.read_statusline_usage(tmp_path / "missing.json") is None


def test_returns_none_on_invalid_json(tmp_path: Path) -> None:
    f = tmp_path / "statusline.json"
    f.write_text("{not json")
    assert statusline.read_statusline_usage(f) is None


def test_parses_full_payload(tmp_path: Path) -> None:
    f = tmp_path / "statusline.json"
    _write(
        f,
        {
            "model": {"id": "claude-opus-4-6", "display_name": "Opus"},
            "rate_limits": {
                "five_hour": {"used_percentage": 23.5, "resets_at": 1900000000},
                "seven_day": {"used_percentage": 41.2, "resets_at": 1900500000},
            },
        },
    )
    usage = statusline.read_statusline_usage(f)
    assert usage is not None
    assert usage.available is True
    assert usage.five_hour_pct == 23.5
    assert usage.seven_day_pct == 41.2
    assert usage.five_hour_resets_at == datetime.fromtimestamp(1900000000, tz=timezone.utc)
    assert usage.seven_day_resets_at == datetime.fromtimestamp(1900500000, tz=timezone.utc)
    assert usage.subscription_type == "claude-code"


def test_handles_missing_rate_limits(tmp_path: Path) -> None:
    f = tmp_path / "statusline.json"
    _write(f, {"model": {"display_name": "Opus"}})
    usage = statusline.read_statusline_usage(f)
    assert usage is not None
    assert usage.available is False
    assert "rate_limits" in usage.error


def test_handles_partial_rate_limits_five_hour_only(tmp_path: Path) -> None:
    f = tmp_path / "statusline.json"
    _write(
        f,
        {
            "rate_limits": {
                "five_hour": {"used_percentage": 10.0, "resets_at": 1900000000},
            }
        },
    )
    usage = statusline.read_statusline_usage(f)
    assert usage is not None
    assert usage.available is True
    assert usage.five_hour_pct == 10.0
    assert usage.seven_day_pct == 0.0
    assert usage.seven_day_resets_at is None


def test_is_still_valid_future_reset() -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=50.0,
        five_hour_resets_at=now + timedelta(hours=1),
        seven_day_pct=20.0,
        seven_day_resets_at=now + timedelta(days=3),
    )
    assert statusline.is_still_valid(usage, now=now) is True


def test_is_still_valid_five_hour_expired_seven_day_not() -> None:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=3.0,
        five_hour_resets_at=now - timedelta(hours=6),
        seven_day_pct=34.0,
        seven_day_resets_at=now + timedelta(days=3),
    )
    assert statusline.is_still_valid(usage, now=now) is True


def test_window_validity_five_expired_seven_valid() -> None:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=3.0,
        five_hour_resets_at=now - timedelta(hours=6),
        seven_day_pct=34.0,
        seven_day_resets_at=now + timedelta(days=3),
    )
    wv = statusline.window_validity(usage, now=now)
    assert wv["overall"] is True
    assert wv["five_valid"] is False
    assert wv["seven_valid"] is True


def test_window_validity_seven_expired_five_valid() -> None:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=3.0,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=34.0,
        seven_day_resets_at=now - timedelta(days=1),
    )
    wv = statusline.window_validity(usage, now=now)
    assert wv["overall"] is True
    assert wv["five_valid"] is True
    assert wv["seven_valid"] is False


def test_window_validity_both_expired() -> None:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=3.0,
        five_hour_resets_at=now - timedelta(hours=6),
        seven_day_pct=34.0,
        seven_day_resets_at=now - timedelta(days=1),
    )
    wv = statusline.window_validity(usage, now=now)
    assert wv["overall"] is False
    assert wv["five_valid"] is False
    assert wv["seven_valid"] is False
    assert "5h window expired" in wv["reason"]
    assert "7d window expired" in wv["reason"]


def test_is_still_valid_all_expired() -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=50.0,
        five_hour_resets_at=now - timedelta(hours=1),
        seven_day_pct=20.0,
        seven_day_resets_at=now - timedelta(days=1),
    )
    assert statusline.is_still_valid(usage, now=now) is False


def test_is_still_valid_none_or_unavailable() -> None:
    assert statusline.is_still_valid(None) is False
    assert statusline.is_still_valid(statusline.ClaudeUsage(available=False)) is False


def test_is_still_valid_stale_file_mtime() -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=10.0,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=5.0,
        seven_day_resets_at=now + timedelta(days=3),
    )
    stale_mtime = now.timestamp() - 7200
    assert statusline.is_still_valid(usage, now=now, file_mtime=stale_mtime) is False


def test_is_still_valid_fresh_file_mtime() -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=10.0,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=5.0,
        seven_day_resets_at=now + timedelta(days=3),
    )
    fresh_mtime = now.timestamp() - 60
    assert statusline.is_still_valid(usage, now=now, file_mtime=fresh_mtime) is True


def test_is_still_valid_no_mtime_skips_check() -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=10.0,
        five_hour_resets_at=now + timedelta(hours=2),
    )
    assert statusline.is_still_valid(usage, now=now, file_mtime=None) is True


def test_is_still_valid_future_file_mtime() -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    usage = statusline.ClaudeUsage(
        available=True,
        five_hour_pct=10.0,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=5.0,
        seven_day_resets_at=now + timedelta(days=3),
    )
    future_mtime = now.timestamp() + 48000
    assert statusline.is_still_valid(usage, now=now, file_mtime=future_mtime) is False


def test_epoch_to_dt_invalid_inputs() -> None:
    assert statusline._epoch_to_dt(None) is None
    assert statusline._epoch_to_dt("not-a-number") is None
    assert statusline._epoch_to_dt(0) == datetime.fromtimestamp(0, tz=timezone.utc)
