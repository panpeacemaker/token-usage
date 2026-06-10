from __future__ import annotations

from datetime import datetime


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


def _reset_suffix(reset, prefix: str = "@") -> str:
    hhmm = _local_hhmm(reset)
    return f"{prefix}{hhmm}" if hhmm else ""


def _select_bar_window(
    data: dict,
    windows: list[tuple[str, str, str, str | None]],
    bar_window: str = "max",
) -> tuple[float, any, str] | None:
    """Return (pct, reset, label) for the driving window, or None.

    If ``bar_window`` names one of the labels in ``windows`` and that window
    has a valid (non-None, coercible, non-expired) pct, it wins. Otherwise
    fall back to the max-pct rule. ``bar_window="max"`` (the default) always
    takes the max-rule path.

    Each window tuple is ``(pct_field, reset_field, label, expired_field)``
    where ``expired_field`` is the optional key in ``data`` that flags an
    expired window (use ``None`` for providers that do not mark expiry).
    """
    if bar_window != "max":
        for pct_field, reset_field, label, expired_field in windows:
            if label != bar_window:
                continue
            if expired_field and data.get(expired_field):
                break
            pct = data.get(pct_field)
            if pct is None:
                break
            try:
                return (float(pct), data.get(reset_field), label)
            except (TypeError, ValueError):
                break
    best = None
    for pct_field, reset_field, label, expired_field in windows:
        if expired_field and data.get(expired_field):
            continue
        pct = data.get(pct_field)
        if pct is None:
            continue
        try:
            pct_val = float(pct)
        except (TypeError, ValueError):
            continue
        reset = data.get(reset_field)
        if best is None or pct_val > best[0]:
            best = (pct_val, reset, label)
    return best


def _format_segment(
    data: dict,
    letter: str,
    windows: list[tuple[str, str, str, str | None]],
    stale: bool = False,
    reset_prefix: str = "@",
    bar_window: str = "max",
) -> str:
    if not data.get("available"):
        return f"{letter} err"
    best = _select_bar_window(data, windows, bar_window=bar_window)
    stale_marker = "*" if stale else ""
    if best is None:
        return f"{letter}0%{stale_marker}"
    pct, reset, _label = best
    return f"{letter}{pct:.0f}%{stale_marker}{_reset_suffix(reset, prefix=reset_prefix)}"


def _format_claude_segment(summary: dict, bar_window: str = "max") -> str:
    windows = [
        ("five_hour_pct", "five_hour_resets_at", "5h", "_five_hour_expired"),
        ("seven_day_pct", "seven_day_resets_at", "7d", "_seven_day_expired"),
    ]
    return _format_segment(summary, "c", windows, stale=summary.get("_stale", False), bar_window=bar_window)


def _format_openai_segment(openai: dict, bar_window: str = "max") -> str:
    windows = [
        ("primary_pct", "primary_reset_at", "primary", None),
        ("weekly_pct", "weekly_reset_at", "weekly", None),
    ]
    return _format_segment(openai, "o", windows, bar_window=bar_window)


def _format_kimi_segment(kimi: dict, bar_window: str = "max") -> str:
    windows = [
        ("primary_pct", "primary_reset_at", "5h", None),
        ("weekly_pct", "weekly_reset_at", "weekly", None),
    ]
    return _format_segment(kimi, "k", windows, bar_window=bar_window)


def _format_opencode_segment(opencode: dict, letter: str = "e", bar_window: str = "max") -> str:
    windows = [
        ("primary_pct", "primary_reset_at", "5h", None),
        ("weekly_pct", "weekly_reset_at", "weekly", None),
    ]
    return _format_segment(opencode, letter, windows, reset_prefix="~", bar_window=bar_window)


def format_compact(
    summary: dict,
    openai: dict | None = None,
    kimi: dict | None = None,
    opencode: dict | None = None,
    opencode_go: dict | None = None,
    weekly_warn_threshold: float = 80.0,
    bare: bool = False,
    bar_windows: dict | None = None,
) -> str:
    bw = bar_windows or {}
    segments: list[str] = []
    if summary:
        segments.append(_format_claude_segment(summary, bar_window=bw.get("claude", "max")))
    if openai is not None:
        segments.append(_format_openai_segment(openai, bar_window=bw.get("openai", "max")))
    if kimi is not None:
        segments.append(_format_kimi_segment(kimi, bar_window=bw.get("kimi", "max")))
    if opencode is not None:
        segments.append(_format_opencode_segment(opencode, letter="e", bar_window=bw.get("opencode", "max")))
    if opencode_go is not None:
        segments.append(_format_opencode_segment(opencode_go, letter="g", bar_window=bw.get("opencode-go", "max")))
    return " ".join(segments)
