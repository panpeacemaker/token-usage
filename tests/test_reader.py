from __future__ import annotations

from pathlib import Path

from token_usage.claude.reader import load_entries

FIXTURES = Path(__file__).parent / "fixtures"


def test_dedup_drops_streaming_duplicates() -> None:
    entries = load_entries(FIXTURES / "streaming_duplicates_dir")
    assert len(entries) == 1


def test_single_block_loads_all() -> None:
    entries = load_entries(FIXTURES / "single_block_dir")
    assert len(entries) == 5


def test_multi_session_loads_all_unique() -> None:
    entries = load_entries(FIXTURES / "multi_session_dir")
    assert len(entries) == 3
