from __future__ import annotations

import time as _time
from datetime import datetime, timezone

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


def _claude_section(summary: dict) -> list[str]:
    lines: list[str] = []
    sub = summary.get("subscription_type", "unknown")
    tier = summary.get("rate_limit_tier", "unknown")
    stale_marker = " [STALE]" if summary.get("_stale") else ""
    lines.append(f"Claude ({sub}) — {tier}{stale_marker}")
    lines.append(DIVIDER)

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

        lines.append(f"  ⏱  5-hour:  {five_pct:5.1f}%   resets {_fmt_local_time(five_reset)}")
        lines.append(f"  📅 7-day:   {seven_pct:5.1f}%   resets {_fmt_local_time(seven_reset)}")

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
            models = ab.get("models") or {}
            lines.append(f"  current block: {_fmt_int(tokens)} tokens")
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
        if wk_toks or wk_msgs:
            lines.append(f"  this week: {wk_msgs} msgs / {_fmt_int(wk_toks)} tokens")

    return lines


def _openai_section(openai: dict) -> list[str]:
    lines: list[str] = ["🟢 ChatGPT Plus", DIVIDER]
    if openai.get("available"):
        primary_reset = _fmt_local_time(_epoch_to_dt(openai.get("primary_reset_at")))
        weekly_reset = _fmt_local_time(_epoch_to_dt(openai.get("weekly_reset_at")))
        lines.append(f"  primary: {openai.get('primary_pct', 0):5.1f}%   resets {primary_reset}")
        if openai.get("weekly_reset_at") is not None or openai.get("weekly_pct"):
            lines.append(f"  weekly:  {openai.get('weekly_pct', 0):5.1f}%   resets {weekly_reset}")
        lines.append(f"  review:  {openai.get('review_pct', 0):5.1f}%")
    else:
        lines.append(f"  ⚠ unavailable: {openai.get('error', 'not configured')}")
    return lines


def _kimi_section(kimi: dict) -> list[str]:
    lines: list[str] = ["🟣 Kimi Code", DIVIDER]
    if kimi.get("available"):
        primary_reset = _fmt_local_time(_epoch_to_dt(kimi.get("primary_reset_at")))
        weekly_reset = _fmt_local_time(_epoch_to_dt(kimi.get("weekly_reset_at")))
        lines.append(f"  5-hour:  {kimi.get('primary_pct', 0):5.1f}%   resets {primary_reset}")
        lines.append(f"  weekly:  {kimi.get('weekly_pct', 0):5.1f}%   resets {weekly_reset}")
    else:
        lines.append(f"  ⚠ unavailable: {kimi.get('error', 'not configured')}")
    return lines


def _opencode_section(opencode: dict, label: str = "OpenCode") -> list[str]:
    pid = opencode.get("provider_id", "opencode")
    lines: list[str] = [f"🟠 {label} ({pid})", DIVIDER]
    if opencode.get("available"):
        primary_reset = _fmt_local_time(_epoch_to_dt(opencode.get("primary_reset_at")))
        weekly_reset = _fmt_local_time(_epoch_to_dt(opencode.get("weekly_reset_at")))
        lines.append(f"  5-hour:  {opencode.get('primary_pct', 0):5.1f}%   resets {primary_reset}")
        lines.append(f"  weekly:  {opencode.get('weekly_pct', 0):5.1f}%   resets {weekly_reset}")
        ptoks = opencode.get("primary_tokens", 0)
        plim = opencode.get("primary_limit_tokens", 0)
        wtoks = opencode.get("weekly_tokens", 0)
        wlim = opencode.get("weekly_limit_tokens", 0)
        if plim:
            lines.append(f"     5h tokens:   {_fmt_int(ptoks)} / {_fmt_int(plim)}")
        if wlim:
            lines.append(f"     wk tokens:   {_fmt_int(wtoks)} / {_fmt_int(wlim)}")
    else:
        lines.append(f"  ⚠ unavailable: {opencode.get('error', 'not configured')}")
    return lines


def format_detail(
    summary: dict | None = None,
    openai: dict | None = None,
    kimi: dict | None = None,
    opencode: dict | None = None,
    opencode_go: dict | None = None,
) -> str:
    sections: list[list[str]] = []
    if summary:
        sections.append(_claude_section(summary))
    if openai is not None:
        sections.append(_openai_section(openai))
    if kimi is not None:
        sections.append(_kimi_section(kimi))
    if opencode is not None:
        sections.append(_opencode_section(opencode, label="OpenCode"))
    if opencode_go is not None:
        sections.append(_opencode_section(opencode_go, label="OpenCode Go"))
    return "\n\n".join("\n".join(section) for section in sections)
