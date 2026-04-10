from __future__ import annotations

import json
import os
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "token-usage"
CACHE_FILE = CACHE_DIR / "summary.json"
CACHE_VERSION = 6


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
    data = read_raw()
    if data is None:
        return None
    if max_age_seconds <= 0:
        return None
    fetched_at = data.get("fetched_at", 0)
    if time.time() - fetched_at > max_age_seconds:
        return None
    return data


def write(payload: dict) -> None:
    data = {
        **payload,
        "_version": CACHE_VERSION,
        "fetched_at": time.time(),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str))
    tmp.replace(CACHE_FILE)
