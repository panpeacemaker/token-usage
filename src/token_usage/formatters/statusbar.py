from __future__ import annotations


def format_compact(summary: dict, openai: dict | None = None) -> str:
    active = summary.get("active_block") or {}
    week = summary.get("week") or {}
    c5 = active.get("pct", 0)
    cw = week.get("pct", 0)

    def fmt_pct(value: float) -> str:
        if value < 1:
            return f"{value:.2f}%"
        if value < 10:
            return f"{value:.1f}%"
        return f"{value:.0f}%"

    parts = [f"🤖 C 5h:{fmt_pct(c5)} W:{fmt_pct(cw)}"]
    if openai and openai.get("available"):
        op = openai.get("primary_pct", 0)
        parts.append(f"O:{fmt_pct(float(op))}")
    return " ".join(parts)
