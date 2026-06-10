from __future__ import annotations

import json
import os
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "token-usage"
CACHE_FILE = CACHE_DIR / "summary.json"
# v8: per-provider `_provider_fetched_at`. v7 used a single top-level
# `fetched_at`, so `--only claude` could refresh it while keeping stale
# ChatGPT/Kimi payloads. Reject anything older.
# v9: added `opencode_go` payload key alongside `opencode`.
# v10: added `_written_at` top-level stamp to detect clock-jump tampering.
CACHE_VERSION = 10


def _age_within(fetched: float, max_age_seconds: int) -> bool:
    """True iff `fetched` is in the past and within `max_age_seconds`.

    A future timestamp (clock skew from suspend/resume or an NTP step) yields a
    negative age; we treat that as stale so the provider gets refetched instead
    of being pinned "fresh" forever.
    """
    if max_age_seconds <= 0:
        return False
    age = time.time() - fetched
    return 0 <= age <= max_age_seconds


def read_raw() -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("_version") != CACHE_VERSION:
        return None
    return data


def read(max_age_seconds: int) -> dict | None:
    """Legacy whole-payload TTL gate.

    Kept for backward compatibility with callers that just want a "globally fresh"
    snapshot. Prefer :func:`read_provider` for per-provider freshness.
    """
    data = read_raw()
    if data is None:
        return None
    try:
        fetched_at = float(data.get("fetched_at", 0) or 0)
    except (TypeError, ValueError):
        return None
    if not _age_within(fetched_at, max_age_seconds):
        return None
    written = data.get("_written_at")
    if isinstance(written, (int, float)) and fetched_at > written:
        return None
    return data


def provider_fetched_at(data: dict | None, name: str) -> float:
    if not data:
        return 0.0
    per = data.get("_provider_fetched_at")
    if isinstance(per, dict):
        val = per.get(name)
        if val is None:
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(data.get("fetched_at", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def is_provider_fresh(data: dict | None, name: str, max_age_seconds: int) -> bool:
    """Return True iff the provider's per-provider stamp is within `max_age_seconds`."""
    if not data:
        return False
    fetched = provider_fetched_at(data, name)
    if fetched <= 0:
        return False
    written = data.get("_written_at")
    if isinstance(written, (int, float)) and fetched > written:
        return False
    return _age_within(fetched, max_age_seconds)


def write(payload: dict, fetched_providers: set[str] | None = None) -> None:
    """Write the cache atomically.

    `fetched_providers` is the set of provider names that were just fetched (or
    attempted) on this tick. Their `_provider_fetched_at` entries are stamped
    `now`. Other providers retain whatever stamp they had in the existing cache
    file so we don't accidentally pretend stale data is fresh.
    """
    now = time.time()
    existing = read_raw() or {}
    existing_per_provider = existing.get("_provider_fetched_at") or {}

    per_provider: dict[str, float] = {}
    for k, v in existing_per_provider.items():
        try:
            ts = float(v)
        except (TypeError, ValueError):
            continue
        if ts <= now:
            per_provider[str(k)] = ts
    if fetched_providers:
        for name in fetched_providers:
            per_provider[name] = now

    payload_no_meta = {k: v for k, v in payload.items() if k not in ("_version", "fetched_at", "_provider_fetched_at", "_written_at")}
    data = {
        **payload_no_meta,
        "_version": CACHE_VERSION,
        "fetched_at": now,
        "_written_at": now,
        "_provider_fetched_at": per_provider,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str))
    tmp.replace(CACHE_FILE)
