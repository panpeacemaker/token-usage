from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from .models import UsageEntry

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def iter_jsonl_files(root: Path | None = None) -> Iterator[Path]:
    root = root or CLAUDE_PROJECTS_DIR
    if not root.exists():
        return
    if root.is_file() and root.suffix == ".jsonl":
        yield root
        return
    yield from root.rglob("*.jsonl")


def _parse_line(line: str) -> UsageEntry | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    msg = data.get("message")
    if not isinstance(msg, dict):
        return None
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None

    ts_str = data.get("timestamp") or ""
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

    message_id = str(msg.get("id") or "")
    request_id = str(data.get("requestId") or "")

    if data.get("isSidechain"):
        kind = "sidechain"
    elif msg.get("stop_reason") == "tool_use":
        kind = "tool"
    else:
        kind = "turn"

    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    cc = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cr = int(usage.get("cache_read_input_tokens", 0) or 0)

    if inp + out + cc + cr == 0:
        return None

    return UsageEntry(
        timestamp=ts.astimezone(timezone.utc),
        message_id=message_id,
        request_id=request_id,
        model=str(msg.get("model") or "unknown"),
        input_tokens=inp,
        output_tokens=out,
        cache_creation_tokens=cc,
        cache_read_tokens=cr,
        kind=kind,
    )


def load_entries(root: Path | None = None) -> list[UsageEntry]:
    seen: set[tuple[str, str]] = set()
    entries: list[UsageEntry] = []

    for fpath in iter_jsonl_files(root):
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                for line in f:
                    entry = _parse_line(line)
                    if entry is None:
                        continue
                    key = (entry.message_id, entry.request_id)
                    if entry.message_id and entry.request_id:
                        if key in seen:
                            continue
                        seen.add(key)
                    entries.append(entry)
        except OSError:
            continue

    entries.sort(key=lambda e: e.timestamp)
    return entries
