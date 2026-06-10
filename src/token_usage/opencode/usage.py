from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path(
    os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
) / "opencode" / "opencode.db"

DEFAULT_PROVIDER_ID = "opencode"


@dataclass
class OpencodeUsage:
    available: bool
    error: str | None = None
    source: str = "sqlite"
    provider_id: str = DEFAULT_PROVIDER_ID
    primary_pct: float = 0.0
    primary_reset_at: int | None = None
    weekly_pct: float = 0.0
    weekly_reset_at: int | None = None
    monthly_pct: float = 0.0
    monthly_reset_at: int | None = None
    primary_tokens: int = 0
    weekly_tokens: int = 0
    monthly_tokens: int = 0
    primary_limit_tokens: int = 0
    weekly_limit_tokens: int = 0
    monthly_limit_tokens: int = 0
    window_kind: str = "rolling"


def _row_tokens(data: dict) -> int:
    tokens = data.get("tokens") or {}
    total = tokens.get("total")
    if total:
        try:
            n = int(total)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    cache = tokens.get("cache") or {}
    parts = (
        tokens.get("input", 0),
        tokens.get("output", 0),
        tokens.get("reasoning", 0),
        cache.get("read", 0),
        cache.get("write", 0),
    )
    out = 0
    for v in parts:
        try:
            out += int(v or 0)
        except (TypeError, ValueError):
            continue
    return out


def _bucket(
    rows: list[tuple[int, int]],
    cutoff_epoch: int,
    window_seconds: int,
) -> tuple[int, int | None]:
    total = 0
    oldest_ms: int | None = None
    for ts_ms, tokens in rows:
        if ts_ms < cutoff_epoch * 1000:
            continue
        total += tokens
        if oldest_ms is None or ts_ms < oldest_ms:
            oldest_ms = ts_ms
    if oldest_ms is None:
        return 0, None
    reset_at = int(oldest_ms / 1000) + window_seconds
    return total, reset_at


def _pct(used: int, limit: int) -> float:
    if limit <= 0:
        return 0.0
    raw = used / limit * 100.0
    if raw < 0:
        return 0.0
    return round(raw, 2)


def fetch_opencode(
    provider_id: str = DEFAULT_PROVIDER_ID,
    db_path: Path | None = None,
    primary_window_hours: int = 5,
    weekly_window_days: int = 7,
    monthly_window_days: int = 30,
    primary_limit_tokens: int = 0,
    weekly_limit_tokens: int = 0,
    monthly_limit_tokens: int = 0,
    now: int | None = None,
) -> OpencodeUsage:
    path = db_path or DEFAULT_DB_PATH
    if not path.exists():
        return OpencodeUsage(
            available=False,
            error=f"opencode db not found: {path}",
            provider_id=provider_id,
        )

    if primary_limit_tokens <= 0 or weekly_limit_tokens <= 0:
        return OpencodeUsage(
            available=False,
            error="opencode primary_limit_tokens/weekly_limit_tokens must be configured",
            provider_id=provider_id,
        )

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        return OpencodeUsage(
            available=False,
            error=f"opencode db open failed: {e}",
            provider_id=provider_id,
        )

    epoch = int(now if now is not None else time.time())
    monthly_seconds = monthly_window_days * 86400
    oldest_needed_ms = (epoch - monthly_seconds) * 1000

    rows: list[tuple[int, int]] = []
    try:
        cursor = conn.execute(
            "SELECT time_created, data FROM message "
            "WHERE json_extract(data, '$.role') = 'assistant' "
            "AND json_extract(data, '$.providerID') = ? "
            "AND time_created >= ?",
            (provider_id, oldest_needed_ms),
        )
        for ts_ms, data_str in cursor:
            try:
                data = json.loads(data_str)
            except (json.JSONDecodeError, TypeError):
                continue
            tokens = _row_tokens(data)
            if tokens <= 0:
                continue
            try:
                rows.append((int(ts_ms), tokens))
            except (TypeError, ValueError):
                continue
    except sqlite3.DatabaseError as e:
        conn.close()
        return OpencodeUsage(
            available=False,
            error=f"opencode db read failed: {e}",
            provider_id=provider_id,
        )
    finally:
        conn.close()

    primary_seconds = primary_window_hours * 3600
    weekly_seconds = weekly_window_days * 86400

    primary_tokens, primary_reset = _bucket(rows, epoch - primary_seconds, primary_seconds)
    weekly_tokens, weekly_reset = _bucket(rows, epoch - weekly_seconds, weekly_seconds)
    monthly_tokens, monthly_reset = _bucket(rows, epoch - monthly_seconds, monthly_seconds)

    return OpencodeUsage(
        available=True,
        provider_id=provider_id,
        primary_pct=_pct(primary_tokens, primary_limit_tokens),
        primary_reset_at=primary_reset,
        weekly_pct=_pct(weekly_tokens, weekly_limit_tokens),
        weekly_reset_at=weekly_reset,
        monthly_pct=_pct(monthly_tokens, monthly_limit_tokens),
        monthly_reset_at=monthly_reset,
        primary_tokens=primary_tokens,
        weekly_tokens=weekly_tokens,
        monthly_tokens=monthly_tokens,
        primary_limit_tokens=primary_limit_tokens,
        weekly_limit_tokens=weekly_limit_tokens,
        monthly_limit_tokens=monthly_limit_tokens,
    )
