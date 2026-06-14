from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(
    os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
) / "opencode" / "opencode.db"

DEFAULT_PROVIDER_ID = "opencode"

WINDOW_PRIMARY = "primary"
WINDOW_WEEKLY = "weekly"
WINDOW_MONTHLY = "monthly"

_PRIMARY_BLOCK_SECONDS = 5 * 3600


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
    window_kind: str = "fixed"
    is_idle: bool = False


def _pos_int(value: object) -> int:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _contains_positive(obj: object) -> bool:
    if isinstance(obj, dict):
        return any(_contains_positive(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_contains_positive(v) for v in obj)
    return _pos_int(obj) > 0


def _row_tokens(data: dict) -> int | None:
    tokens = data.get("tokens")
    # Every real assistant row carries a `tokens` object; a missing or wrongly
    # typed one means the schema drifted → fail loud, never silent-skip.
    if tokens is None or not isinstance(tokens, dict):
        return None

    cache = tokens.get("cache")
    cache = cache if isinstance(cache, dict) else {}

    known = _pos_int(tokens.get("total")) or (
        _pos_int(tokens.get("input"))
        + _pos_int(tokens.get("output"))
        + _pos_int(tokens.get("reasoning"))
        + _pos_int(cache.get("read"))
        + _pos_int(cache.get("write"))
    )
    if known > 0:
        return known

    # known == 0: a genuinely-zero row is a legit skip, but if any positive token
    # number hides under an UNRECOGNIZED key/path inside `tokens`, OR under the
    # alternate top-level `usage` field name, the schema drifted → fail loud.
    for k, v in tokens.items():
        if k in ("total", "input", "output", "reasoning"):
            continue
        if k == "cache":
            for ck, cv in (v.items() if isinstance(v, dict) else []):
                if ck not in ("read", "write") and _contains_positive(cv):
                    return None
            if not isinstance(v, dict) and _contains_positive(v):
                return None
            continue
        if _contains_positive(v):
            return None
    if _contains_positive(data.get("usage")):
        return None
    return 0


def _fixed_window_start(now_epoch: int, window_kind: str) -> int:
    if window_kind == WINDOW_PRIMARY:
        return (now_epoch // _PRIMARY_BLOCK_SECONDS) * _PRIMARY_BLOCK_SECONDS
    dt = datetime.fromtimestamp(now_epoch, tz=timezone.utc)
    if window_kind == WINDOW_WEEKLY:
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = midnight - timedelta(days=dt.weekday())
        return int(monday.timestamp())
    if window_kind == WINDOW_MONTHLY:
        first = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return int(first.timestamp())
    raise ValueError(f"unknown window_kind: {window_kind!r}")


def _fixed_window_reset(now_epoch: int, window_kind: str) -> int:
    start = _fixed_window_start(now_epoch, window_kind)
    if window_kind == WINDOW_PRIMARY:
        return start + _PRIMARY_BLOCK_SECONDS
    if window_kind == WINDOW_WEEKLY:
        return start + 7 * 86400
    start_dt = datetime.fromtimestamp(start, tz=timezone.utc)
    if start_dt.month == 12:
        return int(start_dt.replace(year=start_dt.year + 1, month=1).timestamp())
    return int(start_dt.replace(month=start_dt.month + 1).timestamp())


def _window_tokens(rows: list[tuple[int, int]], window_start_epoch: int) -> int:
    cutoff_ms = window_start_epoch * 1000
    return sum(tokens for ts_ms, tokens in rows if ts_ms >= cutoff_ms)


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
    primary_start = _fixed_window_start(epoch, WINDOW_PRIMARY)
    weekly_start = _fixed_window_start(epoch, WINDOW_WEEKLY)
    monthly_start = _fixed_window_start(epoch, WINDOW_MONTHLY)
    oldest_needed_ms = min(primary_start, weekly_start, monthly_start) * 1000

    rows: list[tuple[int, int]] = []
    malformed = False
    selector_drift = False
    try:
        # Lenient selector: fetch rows matching THIS provider via the canonical
        # keys OR any alternate key name, in one scan. Canonical rows are counted
        # normally; a row that matches only via an alternate selector key while
        # carrying real usage means role/providerID drifted → fail loud (never a
        # silent idle/undercount), even when other canonical rows still exist.
        cursor = conn.execute(
            "SELECT time_created, data FROM message WHERE time_created >= :oldest "
            "AND (json_extract(data, '$.role') = 'assistant' "
            "     OR json_extract(data, '$.type') = 'assistant') "
            "AND (json_extract(data, '$.providerID') = :pid "
            "     OR json_extract(data, '$.provider') = :pid "
            "     OR json_extract(data, '$.provider_id') = :pid)",
            {"oldest": oldest_needed_ms, "pid": provider_id},
        )
        for ts_ms, data_str in cursor:
            try:
                data = json.loads(data_str)
            except (json.JSONDecodeError, TypeError):
                continue
            canonical = data.get("role") == "assistant" and data.get("providerID") == provider_id
            tokens = _row_tokens(data)
            if not canonical:
                if tokens != 0:
                    selector_drift = True
                continue
            if tokens is None:
                malformed = True
                continue
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

    if malformed:
        return OpencodeUsage(
            available=False,
            error="opencode token schema: unrecognized token fields",
            provider_id=provider_id,
        )

    if selector_drift:
        return OpencodeUsage(
            available=False,
            error="opencode schema: role/providerID selector fields renamed",
            provider_id=provider_id,
        )

    primary_tokens = _window_tokens(rows, primary_start)
    weekly_tokens = _window_tokens(rows, weekly_start)
    monthly_tokens = _window_tokens(rows, monthly_start)
    is_idle = primary_tokens == 0 and weekly_tokens == 0

    return OpencodeUsage(
        available=True,
        provider_id=provider_id,
        primary_pct=_pct(primary_tokens, primary_limit_tokens),
        primary_reset_at=_fixed_window_reset(epoch, WINDOW_PRIMARY),
        weekly_pct=_pct(weekly_tokens, weekly_limit_tokens),
        weekly_reset_at=_fixed_window_reset(epoch, WINDOW_WEEKLY),
        monthly_pct=_pct(monthly_tokens, monthly_limit_tokens),
        monthly_reset_at=_fixed_window_reset(epoch, WINDOW_MONTHLY),
        primary_tokens=primary_tokens,
        weekly_tokens=weekly_tokens,
        monthly_tokens=monthly_tokens,
        primary_limit_tokens=primary_limit_tokens,
        weekly_limit_tokens=weekly_limit_tokens,
        monthly_limit_tokens=monthly_limit_tokens,
        is_idle=is_idle,
    )
