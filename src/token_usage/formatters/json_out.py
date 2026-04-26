from __future__ import annotations

import json
from datetime import datetime


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"not serializable: {type(o)}")


def format_json(summary: dict, openai: dict | None = None, kimi: dict | None = None) -> str:
    return json.dumps(
        {"claude": summary, "openai": openai, "kimi": kimi},
        indent=2,
        default=_default,
    )
