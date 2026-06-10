from __future__ import annotations

from datetime import datetime, timedelta

from .models import SessionBlock, UsageEntry

BLOCK_DURATION = timedelta(hours=5)


def _floor_to_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def compute_blocks(entries: list[UsageEntry], block_duration: timedelta = BLOCK_DURATION) -> list[SessionBlock]:
    blocks: list[SessionBlock] = []
    if not entries:
        return blocks

    current: SessionBlock | None = None
    last_ts: datetime | None = None

    for e in entries:
        if current is None:
            start = _floor_to_hour(e.timestamp)
            current = SessionBlock(start=start, end=start + block_duration, entries=[e])
            last_ts = e.timestamp
            continue

        assert last_ts is not None
        time_since_block_start = e.timestamp - current.start
        gap_since_last = e.timestamp - last_ts
        exceeded_window = time_since_block_start >= block_duration
        large_gap = gap_since_last > block_duration

        if exceeded_window or large_gap:
            blocks.append(current)

            if large_gap:
                gap_start = current.start + block_duration
                gap_end = e.timestamp
                if gap_end > gap_start:
                    blocks.append(SessionBlock(start=gap_start, end=gap_end, entries=[], is_gap=True))

            start = _floor_to_hour(e.timestamp)
            current = SessionBlock(start=start, end=start + block_duration, entries=[e])
            last_ts = e.timestamp
        else:
            current.entries.append(e)
            last_ts = e.timestamp

    if current is not None:
        blocks.append(current)

    return blocks
