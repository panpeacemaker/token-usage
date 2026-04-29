from __future__ import annotations

import json
from datetime import datetime, timezone

from token_usage.formatters.json_out import format_json


def test_basic_structure():
    summary = {"available": True, "five_hour_pct": 42.0}
    result = json.loads(format_json(summary))
    assert "claude" in result
    assert "openai" in result
    assert "kimi" in result
    assert "opencode" in result
    assert result["claude"]["five_hour_pct"] == 42.0
    assert result["openai"] is None
    assert result["opencode"] is None


def test_with_opencode():
    summary = {"available": True}
    opencode = {"available": True, "primary_pct": 30.0}
    result = json.loads(format_json(summary, None, None, opencode))
    assert result["opencode"]["primary_pct"] == 30.0


def test_with_opencode_go():
    summary = {"available": True}
    opencode_go = {"available": True, "primary_pct": 50.0}
    result = json.loads(format_json(summary, None, None, None, opencode_go))
    assert result["opencode_go"]["primary_pct"] == 50.0
    assert result["opencode"] is None


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
