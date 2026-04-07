from __future__ import annotations

WEEKLY_WARN_THRESHOLD = 85.0


def format_compact(
    summary: dict,
    openai: dict | None = None,
    weekly_warn_threshold: float = WEEKLY_WARN_THRESHOLD,
) -> str:
    parts: list[str] = ["🤖"]

    if not summary.get("available"):
        parts.append("C err")
    else:
        c_5h = float(summary.get("five_hour_pct", 0) or 0)
        c_week = float(summary.get("seven_day_pct", 0) or 0)
        c_part = f"C {c_5h:.0f}%"
        if c_week >= weekly_warn_threshold:
            c_part += f" w {c_week:.0f}%"
        parts.append(c_part)

    if openai and openai.get("available"):
        o_5h = float(openai.get("primary_pct", 0) or 0)
        o_part = f"O {o_5h:.0f}%"
        if o_5h >= weekly_warn_threshold:
            o_part += f" w {o_5h:.0f}%"
        parts.append("| " + o_part)

    return " ".join(parts)
