from __future__ import annotations

WEEKLY_WARN_THRESHOLD = 85.0


def format_compact(
    summary: dict,
    openai: dict | None = None,
    weekly_warn_threshold: float = WEEKLY_WARN_THRESHOLD,
) -> str:
    """Compact statusbar format.

    Default: '🤖 C {5h%} | O {5h%}'
    If weekly >= threshold for either side, append ' w {week%}' to that side.
    Omits OpenAI section if not available.
    """
    active = summary.get("active_block") or {}
    week = summary.get("week") or {}

    c_5h = float(active.get("pct", 0) or 0)
    c_week = float(week.get("pct_messages", week.get("pct", 0)) or 0)

    c_part = f"C {c_5h:.1f}%"
    if c_week >= weekly_warn_threshold:
        c_part += f" w {c_week:.1f}%"

    parts = [f"🤖 {c_part}"]

    if openai and openai.get("available"):
        o_5h = float(openai.get("primary_pct", 0) or 0)
        o_week = o_5h
        o_part = f"O {o_5h:.1f}%"
        if o_week >= weekly_warn_threshold:
            o_part += f" w {o_week:.1f}%"
        parts.append(o_part)

    return " | ".join(parts)
