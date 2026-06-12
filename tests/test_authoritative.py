from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from token_usage.claude import authoritative as authoritative_mod
from token_usage.claude.models import ClaudeUsage


@pytest.fixture
def lkg_path(tmp_path: Path, monkeypatch):
    path = tmp_path / "claude_lkg.json"
    monkeypatch.setattr(authoritative_mod, "LKG_FILE", path)
    return path


def _usage(five_pct: float = 25.0, seven_pct: float = 10.0) -> ClaudeUsage:
    now = datetime.now(timezone.utc)
    return ClaudeUsage(
        available=True,
        five_hour_pct=five_pct,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=seven_pct,
        seven_day_resets_at=now + timedelta(days=3),
        subscription_type="claude-code",
        rate_limit_tier="max5",
    )


def test_save_load_roundtrip(lkg_path: Path) -> None:
    usage = _usage()
    authoritative_mod.save(usage, "oauth")
    loaded = authoritative_mod.load()
    assert loaded is not None
    loaded_usage, source, saved_at = loaded
    assert source == "oauth"
    assert isinstance(saved_at, float)
    assert loaded_usage.five_hour_pct == usage.five_hour_pct
    assert loaded_usage.five_hour_resets_at == usage.five_hour_resets_at
    assert loaded_usage.seven_day_pct == usage.seven_day_pct
    assert loaded_usage.seven_day_resets_at == usage.seven_day_resets_at
    assert loaded_usage.subscription_type == usage.subscription_type
    assert loaded_usage.rate_limit_tier == usage.rate_limit_tier


def test_missing_file_returns_none(lkg_path: Path) -> None:
    assert authoritative_mod.load() is None


def test_corrupt_json_returns_none(lkg_path: Path) -> None:
    lkg_path.parent.mkdir(parents=True, exist_ok=True)
    lkg_path.write_text("not json")
    assert authoritative_mod.load() is None


def test_incomplete_payload_returns_none(lkg_path: Path) -> None:
    lkg_path.parent.mkdir(parents=True, exist_ok=True)
    lkg_path.write_text(json.dumps({"saved_at": 1.0, "source": "oauth"}))
    assert authoritative_mod.load() is None


def test_deserialized_datetimes_are_utc_aware(lkg_path: Path) -> None:
    usage = _usage()
    authoritative_mod.save(usage, "statusline")
    loaded_usage, _source, _saved_at = authoritative_mod.load()
    assert loaded_usage.five_hour_resets_at is not None
    assert loaded_usage.five_hour_resets_at.tzinfo is not None
    assert loaded_usage.five_hour_resets_at.utcoffset().total_seconds() == 0
