from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import UsageEntry

OPENCODE_DB = Path(
    os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
) / "opencode" / "opencode.db"


def load_entries(db_path: Path | None = None) -> list[UsageEntry]:
    path = db_path or OPENCODE_DB
    if not path.exists():
        return []

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return []

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, time_created, data FROM message "
            "WHERE data LIKE '%\"role\":\"assistant\"%' "
            "   OR data LIKE '%\"role\": \"assistant\"%'"
        )
        entries: list[UsageEntry] = []
        for row in cursor:
            entry = _row_to_entry(row)
            if entry is not None:
                entries.append(entry)
        entries.sort(key=lambda e: e.timestamp)
        return entries
    except sqlite3.DatabaseError:
        return []
    finally:
        conn.close()


def _row_to_entry(row: sqlite3.Row) -> UsageEntry | None:
    try:
        data = json.loads(row["data"])
    except (json.JSONDecodeError, TypeError):
        return None

    if data.get("providerID") != "anthropic":
        return None

    tokens = data.get("tokens") or {}
    input_tokens = int(tokens.get("input", 0) or 0)
    output_tokens = int(tokens.get("output", 0) or 0)
    cache = tokens.get("cache") or {}
    cache_write = int(cache.get("write", 0) or 0)
    cache_read = int(cache.get("read", 0) or 0)

    if input_tokens + output_tokens + cache_write + cache_read == 0:
        return None

    ts_ms = row["time_created"]
    try:
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None

    return UsageEntry(
        timestamp=ts,
        message_id=str(row["id"]),
        request_id="",
        model=str(data.get("modelID") or "unknown"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_write,
        cache_read_tokens=cache_read,
    )
