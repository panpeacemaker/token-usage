from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from token_usage.claude import opencode_reader


def _create_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            data TEXT NOT NULL
        )
    """)
    return conn


def _insert(conn: sqlite3.Connection, msg_id: str, ts_ms: int, data: dict) -> None:
    conn.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
        (msg_id, "ses_test", ts_ms, ts_ms, json.dumps(data)),
    )


def test_returns_empty_when_db_missing(tmp_path: Path) -> None:
    entries = opencode_reader.load_entries(tmp_path / "missing.db")
    assert entries == []


def test_reads_anthropic_assistant_messages(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    ts = int(datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    _insert(
        conn,
        "msg_1",
        ts,
        {
            "role": "assistant",
            "providerID": "anthropic",
            "modelID": "claude-opus-4-6",
            "tokens": {
                "input": 100,
                "output": 50,
                "cache": {"read": 1000, "write": 200},
            },
        },
    )
    conn.commit()
    conn.close()

    entries = opencode_reader.load_entries(db)
    assert len(entries) == 1
    e = entries[0]
    assert e.message_id == "msg_1"
    assert e.model == "claude-opus-4-6"
    assert e.input_tokens == 100
    assert e.output_tokens == 50
    assert e.cache_creation_tokens == 200
    assert e.cache_read_tokens == 1000
    assert e.total_tokens == 1350


def test_skips_non_anthropic_provider(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    ts = int(datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    _insert(
        conn,
        "msg_1",
        ts,
        {
            "role": "assistant",
            "providerID": "github-copilot",
            "modelID": "grok-code-fast-1",
            "tokens": {"input": 100, "output": 50, "cache": {"read": 0, "write": 0}},
        },
    )
    conn.commit()
    conn.close()

    entries = opencode_reader.load_entries(db)
    assert entries == []


def test_skips_user_messages(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    ts = int(datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    _insert(
        conn,
        "msg_1",
        ts,
        {"role": "user", "content": "hello"},
    )
    conn.commit()
    conn.close()

    entries = opencode_reader.load_entries(db)
    assert entries == []


def test_skips_zero_token_messages(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    ts = int(datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    _insert(
        conn,
        "msg_1",
        ts,
        {
            "role": "assistant",
            "providerID": "anthropic",
            "modelID": "claude-opus-4-6",
            "tokens": {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}},
        },
    )
    conn.commit()
    conn.close()

    entries = opencode_reader.load_entries(db)
    assert entries == []


def test_sorts_by_timestamp(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = _create_db(db)
    t1 = int(datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    t2 = int(datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc).timestamp() * 1000)
    _insert(
        conn,
        "msg_2",
        t2,
        {
            "role": "assistant",
            "providerID": "anthropic",
            "modelID": "claude-opus-4-6",
            "tokens": {"input": 100, "output": 50, "cache": {"read": 0, "write": 0}},
        },
    )
    _insert(
        conn,
        "msg_1",
        t1,
        {
            "role": "assistant",
            "providerID": "anthropic",
            "modelID": "claude-opus-4-6",
            "tokens": {"input": 200, "output": 100, "cache": {"read": 0, "write": 0}},
        },
    )
    conn.commit()
    conn.close()

    entries = opencode_reader.load_entries(db)
    assert [e.message_id for e in entries] == ["msg_1", "msg_2"]
