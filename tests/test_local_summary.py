from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from token_usage.claude import local_summary
from token_usage.claude.limits import get_limits


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def _entry(ts: str, msg_id: str, req_id: str, tokens: int) -> dict:
    return {
        "timestamp": ts,
        "requestId": req_id,
        "message": {
            "id": msg_id,
            "model": "claude-sonnet-4-6",
            "usage": {
                "input_tokens": tokens,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    }


def test_empty_directory_returns_unavailable(tmp_path: Path) -> None:
    limits = get_limits("pro")
    usage, detail = local_summary.compute_local(
        limits,
        root=tmp_path,
        opencode_db=tmp_path / "missing.db",
    )
    assert usage.available is False
    assert "no local" in usage.error.lower()
    assert detail.get("total_entries") == 0


def test_populated_directory_returns_usage(tmp_path: Path) -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    ts = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    _write_jsonl(
        tmp_path / "sess.jsonl",
        [
            _entry(ts, "msg-1", "req-1", 1000),
            _entry(ts, "msg-2", "req-2", 2000),
        ],
    )
    limits = get_limits("pro", {"pro": {"tokens_5h": 10000}})
    usage, detail = local_summary.compute_local(
        limits,
        now=now,
        root=tmp_path,
        opencode_db=tmp_path / "missing.db",
    )

    assert usage.available is True
    assert usage.subscription_type == "local"
    assert usage.rate_limit_tier == "pro"
    assert usage.five_hour_pct > 0
    assert usage.five_hour_resets_at is not None
    assert usage.five_hour_resets_at > now
    assert usage.seven_day_resets_at is not None
    assert usage.seven_day_resets_at > now
    assert usage.seven_day_resets_at <= now + timedelta(days=7)
    assert detail["active_block"]["tokens"] == 3000


def test_weekly_pct_uses_max_of_tokens_and_messages(tmp_path: Path) -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    ts = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    _write_jsonl(
        tmp_path / "sess.jsonl",
        [_entry(ts, f"msg-{i}", f"req-{i}", 100) for i in range(5)],
    )
    limits = get_limits("pro", {"pro": {"tokens_weekly": 1000, "messages_weekly": 10}})
    usage, _ = local_summary.compute_local(
        limits,
        now=now,
        root=tmp_path,
        opencode_db=tmp_path / "missing.db",
    )
    assert usage.available is True
    assert usage.seven_day_pct == 50.0


def test_fallback_five_h_reset_when_no_active_block(tmp_path: Path) -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    old_ts = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    _write_jsonl(
        tmp_path / "sess.jsonl",
        [_entry(old_ts, "msg-old", "req-old", 1000)],
    )
    limits = get_limits("pro")
    usage, _ = local_summary.compute_local(
        limits,
        now=now,
        root=tmp_path,
        opencode_db=tmp_path / "missing.db",
    )
    assert usage.available is True
    assert usage.five_hour_resets_at is not None
    assert usage.five_hour_resets_at >= now + timedelta(hours=4, minutes=59)
