from __future__ import annotations

import json
from datetime import datetime, timezone

from token_usage.formatters.json_out import format_json


def test_basic_structure():
    summary = {"available": True, "five_hour_pct": 42.0}
    result = json.loads(format_json(summary))
    assert "claude" in result
    assert "openai" in result
    assert result["claude"]["five_hour_pct"] == 42.0
    assert result["openai"] is None


def test_with_openai():
    summary = {"available": True}
    openai = {"available": True, "primary_pct": 30.0}
    result = json.loads(format_json(summary, openai))
    assert result["openai"]["primary_pct"] == 30.0


def test_datetime_serialization():
    dt = datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc)
    summary = {"resets_at": dt}
    result = json.loads(format_json(summary))
    assert "2026-04-10" in result["claude"]["resets_at"]
