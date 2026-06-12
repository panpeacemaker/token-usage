"""Shared pytest fixtures and helpers for the token-usage test suite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from token_usage.claude.models import UsageEntry


# ---------------------------------------------------------------------------
# UsageEntry / JSONL helpers
# ---------------------------------------------------------------------------


def make_usage_entry(
    ts: datetime,
    *,
    tokens: int = 1000,
    message_id: str | None = None,
    request_id: str = "req",
    model: str = "claude-sonnet-4-6",
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> UsageEntry:
    """Build a UsageEntry with sensible defaults for tests.

    The default ``message_id`` is derived from the timestamp so callers do
    not have to invent unique ids when they don't care about uniqueness.
    """
    return UsageEntry(
        timestamp=ts,
        message_id=message_id if message_id is not None else f"msg_{ts.timestamp()}",
        request_id=request_id,
        model=model,
        input_tokens=tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
    )


def make_jsonl_record(
    ts: str,
    msg_id: str,
    req_id: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation: int = 0,
    cache_read: int = 0,
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Build a Claude Code JSONL message record."""
    return {
        "timestamp": ts,
        "requestId": req_id,
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            },
        },
    }


def write_jsonl(path: Path, records: list[dict]) -> None:
    """Write a list of dicts as a JSONL file (one JSON object per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_lkg_file(tmp_path, monkeypatch):
    """Redirect the claude last-known-good store to a temp file for ALL tests.

    Without this, any test exercising _select_claude_source with a successful
    statusline/oauth fixture writes fixture data (year-2099 resets!) into the
    user's real ~/.cache/token-usage/claude_lkg.json, which the LKG fallback
    tier would then serve as authoritative forever.
    """
    from token_usage.claude import authoritative

    monkeypatch.setattr(authoritative, "LKG_FILE", tmp_path / "claude_lkg.json")


@pytest.fixture
def utc_now() -> datetime:
    """A stable UTC reference timestamp used by deterministic tests."""
    return datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def make_entry():
    """Factory fixture exposing :func:`make_usage_entry` to tests."""
    return make_usage_entry


@pytest.fixture
def make_record():
    """Factory fixture exposing :func:`make_jsonl_record` to tests."""
    return make_jsonl_record


@pytest.fixture
def write_jsonl_file():
    """Factory fixture exposing :func:`write_jsonl` to tests."""
    return write_jsonl
