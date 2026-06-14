from __future__ import annotations

import time as _time
from datetime import datetime, timezone
from typing import Any

from ._shared import _select_bar_window

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━"


def _fmt_local_time(value: datetime | str | int | float | None) -> str:
    if value is None:
        return "—"
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            dt = _epoch_to_dt(value)
            if dt is None:
                return "—"
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value)
        else:
            dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%a %H:%M")
    except (ValueError, TypeError, OSError, OverflowError, AttributeError):
        return str(value)


def _fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def _epoch_to_dt(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _fmt_age_seconds(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60}m"


def _fmt_source_detail(source_detail: dict) -> str:
    chosen = source_detail.get("chosen", "unknown")
    rejected = source_detail.get("rejected", [])
    parts: list[str] = []
    for r in rejected:
        src = r.get("source", "")
        reason = r.get("reason", "")
        short = reason
        if reason == "file missing":
            short = "missing"
        elif reason and reason.startswith("file age"):
            short = "stale"
        elif reason and "window expired" in reason:
            short = "expired"
        elif reason and reason.startswith("unavailable:"):
            short = reason.split(":", 1)[1].strip()
        elif reason == "unavailable":
            short = "unavailable"
        parts.append(f"{src}: {short}")
    if parts:
        return f"source: {chosen} ({'; '.join(parts)})"
    return f"source: {chosen}"



def _bar_marker(label: str, bar_window: tuple[float, Any, str] | None) -> str:
    if bar_window is None:
        return ""
    _pct, _reset, bar_label = bar_window
    if bar_label == label:
        return "  ← bar"
    return ""


def _claude_section(summary: dict, bar_window: str = "max") -> list[str]:
    lines: list[str] = []
    sub = summary.get("subscription_type", "unknown")
    tier = summary.get("rate_limit_tier", "unknown")
    stale_marker = " [STALE]" if summary.get("_stale") else ""
    lines.append(f"Claude ({sub}) — {tier}{stale_marker}")
    lines.append(DIVIDER)

    source_detail = summary.get("_source_detail")
    if source_detail:
        lines.append(f"  {_fmt_source_detail(source_detail)}")

    if summary.get("_stale"):
        reason = summary.get("_stale_reason", "unknown")
        fetched_at = summary.get("_fetched_at")
        retry_at = summary.get("_retry_at")
        if fetched_at:
            age = _time.time() - float(fetched_at)
            lines.append(f"  ⚠ showing cached data ({_fmt_age_seconds(age)} old)")
        else:
            lines.append("  ⚠ showing cached data")
        lines.append(f"     reason: {reason}")
        if retry_at:
            eta = float(retry_at) - _time.time()
            if eta > 0:
                lines.append(f"     next retry in: {_fmt_age_seconds(eta)}")

    if not summary.get("available"):
        lines.append(f"  ⚠ unavailable: {summary.get('error', 'unknown')}")
    else:
        five_pct = summary.get("five_hour_pct", 0)
        five_reset = summary.get("five_hour_resets_at")
        seven_pct = summary.get("seven_day_pct", 0)
        seven_reset = summary.get("seven_day_resets_at")
        five_expired = summary.get("_five_hour_expired")
        seven_expired = summary.get("_seven_day_expired")

        windows = [
            ("five_hour_pct", "five_hour_resets_at", "5h", "_five_hour_expired"),
            ("seven_day_pct", "seven_day_resets_at", "7d", "_seven_day_expired"),
        ]
        bar = _select_bar_window(summary, windows, bar_window=bar_window)

        five_estimate = summary.get("_five_hour_estimate")
        seven_estimate = summary.get("_seven_day_estimate")

        if five_expired:
            lines.append("  ⏱  5-hour:  ?       expired")
        else:
            marker = _bar_marker("5h", bar)
            est = " (estimate)" if five_estimate else ""
            lines.append(f"  ⏱  5-hour:  {five_pct:5.1f}%   resets {_fmt_local_time(five_reset)}{marker}{est}")
        if seven_expired:
            lines.append("  📅 7-day:   ?       expired")
        else:
            marker = _bar_marker("7d", bar)
            est = " (estimate)" if seven_estimate else ""
            lines.append(f"  📅 7-day:   {seven_pct:5.1f}%   resets {_fmt_local_time(seven_reset)}{marker}{est}")

        opus_pct = summary.get("seven_day_opus_pct")
        if opus_pct is not None:
            lines.append(f"     └ opus:   {opus_pct:5.1f}%")
        sonnet_pct = summary.get("seven_day_sonnet_pct")
        if sonnet_pct is not None:
            lines.append(f"     └ sonnet: {sonnet_pct:5.1f}%")

    local = summary.get("local")
    if local and not local.get("error"):
        ab = local.get("active_block") or {}
        wk = local.get("week") or {}
        lines.append("")
        lines.append("Local JSONL stats:")
        if ab.get("present"):
            tokens = ab.get("tokens", 0)
            cache_read = ab.get("cache_read_tokens", 0)
            effective = ab.get("effective_tokens")
            crw = ab.get("cache_read_weight")
            models = ab.get("models") or {}
            cache_part = f" (+{_fmt_int(cache_read)} cache-read)" if cache_read else ""
            lines.append(f"  current block: {_fmt_int(tokens)} tokens{cache_part}")
            if effective is not None and crw is not None and cache_read:
                w = f"{crw:.1f}"
                lines.append(
                    f"     effective: {_fmt_int(effective)}"
                    f" (billed {_fmt_int(tokens)} + cache-read {_fmt_int(cache_read)} \u00d7 {w})"
                )
            if models:
                merged: dict[str, int] = {}
                for m, t in models.items():
                    short = m.split("-")[1] if "-" in m else m
                    merged[short] = merged.get(short, 0) + int(t)
                top = sorted(merged.items(), key=lambda kv: -kv[1])[:3]
                for short, t in top:
                    lines.append(f"     {short}: {_fmt_int(t)}")
        wk_msgs = wk.get("messages", 0)
        wk_toks = wk.get("tokens", 0)
        wk_cache = wk.get("cache_read_tokens", 0)
        wk_eff = wk.get("effective_tokens")
        wk_crw = wk.get("cache_read_weight")
        if wk_toks or wk_msgs or wk_cache:
            cache_part = f" (+{_fmt_int(wk_cache)} cache-read)" if wk_cache else ""
            lines.append(f"  this week: {wk_msgs} msgs / {_fmt_int(wk_toks)} tokens{cache_part}")
            if wk_eff is not None and wk_crw is not None and wk_cache:
                w = f"{wk_crw:.1f}"
                lines.append(
                    f"     effective: {_fmt_int(wk_eff)}"
                    f" (billed {_fmt_int(wk_toks)} + cache-read {_fmt_int(wk_cache)} \u00d7 {w})"
                )

    return lines


def _openai_section(openai: dict, bar_window: str = "max") -> list[str]:
    lines: list[str] = ["🟢 ChatGPT Plus", DIVIDER]
    if openai.get("available"):
        primary_reset = _fmt_local_time(_epoch_to_dt(openai.get("primary_reset_at")))
        weekly_reset = _fmt_local_time(_epoch_to_dt(openai.get("weekly_reset_at")))
        windows = [
            ("primary_pct", "primary_reset_at", "primary", None),
            ("weekly_pct", "weekly_reset_at", "weekly", None),
        ]
        bar = _select_bar_window(openai, windows, bar_window=bar_window)
        marker = _bar_marker("primary", bar)
        lines.append(f"  primary: {openai.get('primary_pct', 0):5.1f}%   resets {primary_reset}{marker}")
        if openai.get("weekly_reset_at") is not None or openai.get("weekly_pct"):
            marker = _bar_marker("weekly", bar)
            lines.append(f"  weekly:  {openai.get('weekly_pct', 0):5.1f}%   resets {weekly_reset}{marker}")
        lines.append(f"  review:  {openai.get('review_pct', 0):5.1f}%")
    else:
        lines.append(f"  ⚠ unavailable: {openai.get('error', 'not configured')}")
    return lines


def _kimi_section(kimi: dict, bar_window: str = "max") -> list[str]:
    lines: list[str] = ["🟣 Kimi Code", DIVIDER]
    if kimi.get("available"):
        primary_reset = _fmt_local_time(_epoch_to_dt(kimi.get("primary_reset_at")))
        weekly_reset = _fmt_local_time(_epoch_to_dt(kimi.get("weekly_reset_at")))
        windows = [
            ("primary_pct", "primary_reset_at", "5h", None),
            ("weekly_pct", "weekly_reset_at", "weekly", None),
        ]
        bar = _select_bar_window(kimi, windows, bar_window=bar_window)
        marker = _bar_marker("5h", bar)
        lines.append(f"  5-hour:  {kimi.get('primary_pct', 0):5.1f}%   resets {primary_reset}{marker}")
        marker = _bar_marker("weekly", bar)
        lines.append(f"  weekly:  {kimi.get('weekly_pct', 0):5.1f}%   resets {weekly_reset}{marker}")
    else:
        lines.append(f"  ⚠ unavailable: {kimi.get('error', 'not configured')}")
    return lines


def _opencode_section(opencode: dict, label: str = "OpenCode", bar_window: str = "max") -> list[str]:
    pid = opencode.get("provider_id", "opencode")
    lines: list[str] = [f"🟠 {label} ({pid})", DIVIDER]
    if not opencode.get("available"):
        lines.append(f"  ⚠ unavailable: {opencode.get('error', 'not configured')}")
        return lines

    window_kind = opencode.get("window_kind", "rolling")
    is_idle = opencode.get("is_idle", False)

    primary_reset = _fmt_local_time(_epoch_to_dt(opencode.get("primary_reset_at")))
    weekly_reset = _fmt_local_time(_epoch_to_dt(opencode.get("weekly_reset_at")))
    monthly_reset = _fmt_local_time(_epoch_to_dt(opencode.get("monthly_reset_at")))

    def _wlabel(reset_str: str) -> str:
        if reset_str == "—":
            return "—"
        if window_kind == "fixed":
            return f"{reset_str} (fixed)"
        return f"~{reset_str} (rolling)"

    primary_label = _wlabel(primary_reset)
    weekly_label = _wlabel(weekly_reset)
    monthly_label = _wlabel(monthly_reset)

    windows = [
        ("primary_pct", "primary_reset_at", "5h", None),
        ("weekly_pct", "weekly_reset_at", "weekly", None),
        ("monthly_pct", "monthly_reset_at", "monthly", None),
    ]
    bar = _select_bar_window(opencode, windows, bar_window=bar_window)

    if is_idle:
        lines.append("  ⏼ idle — no activity in 5h/weekly windows")
    else:
        marker = _bar_marker("5h", bar)
        lines.append(f"  5-hour:  {opencode.get('primary_pct', 0):5.1f}%   resets {primary_label}{marker}")
        marker = _bar_marker("weekly", bar)
        lines.append(f"  weekly:  {opencode.get('weekly_pct', 0):5.1f}%   resets {weekly_label}{marker}")

    mlim = opencode.get("monthly_limit_tokens", 0)
    if mlim:
        marker = "" if is_idle else _bar_marker("monthly", bar)
        lines.append(f"  monthly: {opencode.get('monthly_pct', 0):5.1f}%   resets {monthly_label}{marker}")
    else:
        lines.append(f"  monthly: —       resets {monthly_label}")

    ptoks = opencode.get("primary_tokens", 0)
    plim = opencode.get("primary_limit_tokens", 0)
    wtoks = opencode.get("weekly_tokens", 0)
    wlim = opencode.get("weekly_limit_tokens", 0)
    mtoks = opencode.get("monthly_tokens", 0)
    if not is_idle:
        if plim:
            lines.append(f"     5h tokens:   {_fmt_int(ptoks)} / {_fmt_int(plim)}")
        if wlim:
            lines.append(f"     wk tokens:   {_fmt_int(wtoks)} / {_fmt_int(wlim)}")
    lines.append(f"     mo tokens:   {_fmt_int(mtoks)} / {_fmt_int(mlim) if mlim else '—'}")
    return lines


def format_detail(
    summary: dict | None = None,
    openai: dict | None = None,
    kimi: dict | None = None,
    opencode: dict | None = None,
    opencode_go: dict | None = None,
    bar_windows: dict | None = None,
) -> str:
    bw = bar_windows or {}
    sections: list[list[str]] = []
    if summary:
        sections.append(_claude_section(summary, bar_window=bw.get("claude", "max")))
    if openai is not None:
        sections.append(_openai_section(openai, bar_window=bw.get("openai", "max")))
    if kimi is not None:
        sections.append(_kimi_section(kimi, bar_window=bw.get("kimi", "max")))
    if opencode is not None:
        sections.append(_opencode_section(opencode, label="OpenCode", bar_window=bw.get("opencode", "max")))
    if opencode_go is not None:
        sections.append(_opencode_section(opencode_go, label="OpenCode Go", bar_window=bw.get("opencode-go", "max")))
    return "\n\n".join("\n".join(section) for section in sections)
