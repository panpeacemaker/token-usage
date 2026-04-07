from __future__ import annotations


def format_compact(summary: dict, openai: dict | None = None) -> str:
    active = summary.get("active_block") or {}
    week = summary.get("week") or {}
    c5 = active.get("pct", 0)
    cw = week.get("pct", 0)

    parts = [f"🤖 C 5h:{c5:.0f}% W:{cw:.0f}%"]
    if openai and openai.get("available"):
        op = openai.get("primary_pct", 0)
        parts.append(f"O:{op:.0f}%")
    return " ".join(parts)
