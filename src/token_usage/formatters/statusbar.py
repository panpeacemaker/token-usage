from __future__ import annotations

from datetime import datetime

WEEKLY_WARN_THRESHOLD = 85.0


def _local_hhmm(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return ""
    if not isinstance(value, datetime):
        return ""
    try:
        return value.astimezone().strftime("%H:%M")
    except (ValueError, OSError):
        return ""


def _format_claude_segment(summary: dict, weekly_warn_threshold: float) -> str:
    if not summary.get("available"):
        return "C err"

    c_5h = float(summary.get("five_hour_pct", 0) or 0)
    c_week = float(summary.get("seven_day_pct", 0) or 0)
    reset = _local_hhmm(summary.get("five_hour_resets_at"))
    stale_marker = "*" if summary.get("_stale") else ""

    out = f"C {c_5h:.0f}%{stale_marker}"
    if c_week >= weekly_warn_threshold:
        out += f" w {c_week:.0f}%"
    if reset:
        out += f" @{reset}"
    return out


def _format_openai_segment(openai: dict, weekly_warn_threshold: float) -> str:
    o_5h = float(openai.get("primary_pct", 0) or 0)
    out = f"O {o_5h:.0f}%"
    if o_5h >= weekly_warn_threshold:
        out += f" w {o_5h:.0f}%"
    return out


def format_compact(
    summary: dict,
    openai: dict | None = None,
    weekly_warn_threshold: float = WEEKLY_WARN_THRESHOLD,
) -> str:
    segments: list[str] = [_format_claude_segment(summary, weekly_warn_threshold)]

    if openai and openai.get("available"):
        segments.append(_format_openai_segment(openai, weekly_warn_threshold))

    return "| " + " | ".join(segments) + " "
