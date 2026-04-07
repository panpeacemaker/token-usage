from __future__ import annotations

import json
import os
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "token-usage"
CACHE_FILE = CACHE_DIR / "summary.json"
CACHE_VERSION = 2


def read(max_age_seconds: int) -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age > max_age_seconds:
            return None
        data = json.loads(CACHE_FILE.read_text())
        if data.get("_version") != CACHE_VERSION:
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def write(data: dict) -> None:
    payload = {**data, "_version": CACHE_VERSION}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(CACHE_FILE)
