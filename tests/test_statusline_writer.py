from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

from token_usage import statusline_writer


def _run(payload: dict, tmp_path: Path, capsys) -> tuple[int, str]:
    target = tmp_path / "statusline.json"
    with patch.object(statusline_writer, "STATUSLINE_CACHE_FILE", target):
        with patch("sys.stdin", io.StringIO(json.dumps(payload))):
            rc = statusline_writer.main([])
    captured = capsys.readouterr()
    return rc, captured.out


def test_writes_cache_atomically(tmp_path: Path, capsys) -> None:
    payload = {
        "model": {"display_name": "Opus"},
        "rate_limits": {
            "five_hour": {"used_percentage": 23.5, "resets_at": 1900000000},
            "seven_day": {"used_percentage": 41.2, "resets_at": 1900500000},
        },
        "cost": {"total_cost_usd": 1.23},
        "context_window": {"used_percentage": 15},
    }
    rc, out = _run(payload, tmp_path, capsys)
    assert rc == 0
    cache_path = tmp_path / "statusline.json"
    assert cache_path.exists()
    written = json.loads(cache_path.read_text())
    assert written == payload


def test_prints_formatted_status(tmp_path: Path, capsys) -> None:
    payload = {
        "model": {"display_name": "Sonnet 4.5"},
        "rate_limits": {
            "five_hour": {"used_percentage": 23.5},
            "seven_day": {"used_percentage": 41.2},
        },
        "cost": {"total_cost_usd": 1.234},
        "context_window": {"used_percentage": 15},
    }
    _, out = _run(payload, tmp_path, capsys)
    assert "[Sonnet 4.5]" in out
    assert "5h 24%" in out
    assert "7d 41%" in out
    assert "ctx 15%" in out
    assert "$1.23" in out


def test_handles_missing_rate_limits(tmp_path: Path, capsys) -> None:
    payload = {"model": {"display_name": "Opus"}}
    rc, out = _run(payload, tmp_path, capsys)
    assert rc == 0
    assert "[Opus]" in out
    assert "5h" not in out
    assert "7d" not in out


def test_handles_empty_stdin(tmp_path: Path, capsys) -> None:
    target = tmp_path / "statusline.json"
    with patch.object(statusline_writer, "STATUSLINE_CACHE_FILE", target):
        with patch("sys.stdin", io.StringIO("")):
            rc = statusline_writer.main([])
    assert rc == 1
    assert not target.exists()


def test_handles_invalid_json(tmp_path: Path, capsys) -> None:
    target = tmp_path / "statusline.json"
    with patch.object(statusline_writer, "STATUSLINE_CACHE_FILE", target):
        with patch("sys.stdin", io.StringIO("{not json")):
            rc = statusline_writer.main([])
    assert rc == 1
    assert not target.exists()
