from __future__ import annotations

from datetime import datetime

WEEKLY_WARN_THRESHOLD = 85.0


def _coerce_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).astimezone()
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _local_hhmm(value) -> str:
    dt = _coerce_dt(value)
    if dt is None:
        return ""
    try:
        return dt.astimezone().strftime("%H:%M")
    except (ValueError, OSError):
        return ""


def _local_day_hhmm(value) -> str:
    dt = _coerce_dt(value)
    if dt is None:
        return ""
    try:
        return dt.astimezone().strftime("%a%H:%M")
    except (ValueError, OSError):
        return ""


def _weekly_warn_suffix(week_pct: float, weekly_reset, threshold: float) -> str:
    if week_pct < threshold:
        return ""
    out = f" w {week_pct:.0f}%"
    week_reset = _local_day_hhmm(weekly_reset)
    if week_reset:
        out += f" @{week_reset}"
    return out


def _format_claude_segment(summary: dict, weekly_warn_threshold: float) -> str:
    if not summary.get("available"):
        return "C err"

    c_5h = float(summary.get("five_hour_pct", 0) or 0)
    c_week = float(summary.get("seven_day_pct", 0) or 0)
    reset = _local_hhmm(summary.get("five_hour_resets_at"))
    stale_marker = "*" if summary.get("_stale") else ""

    out = f"C {c_5h:.0f}%{stale_marker}"
    out += _weekly_warn_suffix(c_week, summary.get("seven_day_resets_at"), weekly_warn_threshold)
    if reset:
        out += f" @{reset}"
    return out


def _format_openai_segment(openai: dict, weekly_warn_threshold: float) -> str:
    if not openai.get("available"):
        return "O err"
    o_5h = float(openai.get("primary_pct", 0) or 0)
    o_week = float(openai.get("weekly_pct", 0) or 0)
    reset = _local_hhmm(openai.get("primary_reset_at"))
    out = f"O {o_5h:.0f}%"
    out += _weekly_warn_suffix(o_week, openai.get("weekly_reset_at"), weekly_warn_threshold)
    if reset:
        out += f" @{reset}"
    return out


def _format_kimi_segment(kimi: dict, weekly_warn_threshold: float) -> str:
    if not kimi.get("available"):
        return "K err"
    k_5h = float(kimi.get("primary_pct", 0) or 0)
    k_week = float(kimi.get("weekly_pct", 0) or 0)
    reset = _local_hhmm(kimi.get("primary_reset_at"))
    out = f"K {k_5h:.0f}%"
    out += _weekly_warn_suffix(k_week, kimi.get("weekly_reset_at"), weekly_warn_threshold)
    if reset:
        out += f" @{reset}"
    return out


def format_compact(
    summary: dict,
    openai: dict | None = None,
    kimi: dict | None = None,
    weekly_warn_threshold: float = WEEKLY_WARN_THRESHOLD,
    bare: bool = False,
) -> str:
    segments: list[str] = []
    if summary:
        segments.append(_format_claude_segment(summary, weekly_warn_threshold))
    if openai is not None:
        segments.append(_format_openai_segment(openai, weekly_warn_threshold))
    if kimi is not None:
        segments.append(_format_kimi_segment(kimi, weekly_warn_threshold))
    if not segments:
        return ""
    if bare:
        return " | ".join(segments)
    return "| " + " | ".join(segments) + " "
