from __future__ import annotations

from datetime import datetime, timedelta, timezone

from token_usage.claude.blocks import compute_blocks
from token_usage.claude.models import UsageEntry


def _entry(ts: datetime, tokens: int = 1000) -> UsageEntry:
    return UsageEntry(
        timestamp=ts,
        message_id=f"msg_{ts.timestamp()}",
        request_id="req",
        model="claude-sonnet-4-6",
        input_tokens=tokens,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
    )


def test_single_block() -> None:
    base = datetime(2026, 4, 5, 10, 15, tzinfo=timezone.utc)
    entries = [_entry(base + timedelta(minutes=i * 30)) for i in range(5)]
    blocks = compute_blocks(entries)
    assert len(blocks) == 1
    assert blocks[0].start.minute == 0
    assert blocks[0].start.hour == 10
    assert blocks[0].total_tokens == 5000


def test_new_block_after_5h() -> None:
    base = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
    entries = [_entry(base), _entry(base + timedelta(hours=6))]
    blocks = compute_blocks(entries)
    assert len([b for b in blocks if not b.is_gap]) == 2
    assert any(b.is_gap for b in blocks)


def test_gap_block_inserted_when_gap_exceeds_5h() -> None:
    base = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
    entries = [_entry(base), _entry(base + timedelta(hours=7))]
    blocks = compute_blocks(entries)
    assert sum(1 for b in blocks if b.is_gap) == 1


def test_gap_uses_block_end_not_last_entry() -> None:
    base = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
    entries = [
        _entry(base),
        _entry(base + timedelta(minutes=5)),
        _entry(base + timedelta(hours=6)),
    ]
    blocks = compute_blocks(entries)
    gaps = [b for b in blocks if b.is_gap]
    assert len(gaps) == 1
    assert gaps[0].start == base + timedelta(hours=5)
    assert gaps[0].end == base + timedelta(hours=6)
