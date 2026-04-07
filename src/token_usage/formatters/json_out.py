from __future__ import annotations

import json


def format_json(summary: dict, openai: dict | None = None) -> str:
    return json.dumps({"claude": summary, "openai": openai}, indent=2, default=str)
