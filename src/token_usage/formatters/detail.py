from __future__ import annotations

from datetime import datetime


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_ts(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%H:%M")
    except Exception:
        return iso


def format_detail(summary: dict, openai: dict | None = None) -> str:
    active = summary.get("active_block") or {}
    week = summary.get("week") or {}
    plan = summary.get("plan", "pro")

    lines: list[str] = []
    lines.append(f"🤖 Claude ({plan}) — Usage")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")

    if active.get("present"):
        lines.append(f"⏱  5h block  {active['pct']:.1f}%  ({_fmt_int(active['tokens'])} / {_fmt_int(active['limit_tokens'])} tok)")
        lines.append(f"   started {_fmt_ts(active.get('start_utc'))}  ends {_fmt_ts(active.get('end_utc'))}")
        models = active.get("models") or {}
        if models:
            top = sorted(models.items(), key=lambda kv: -kv[1])[:3]
            lines.append("   models: " + ", ".join(f"{m.split('-')[1] if '-' in m else m}:{_fmt_int(t)}" for m, t in top))
    else:
        lines.append("⏱  5h block  idle")

    lines.append("")
    lines.append(f"📅 Week     {week.get('pct', 0):.1f}%  ({_fmt_int(week.get('tokens', 0))} / {_fmt_int(week.get('limit_tokens', 0))} tok)")
    lines.append(f"   messages  {week.get('pct_messages', 0):.1f}%  ({week.get('messages', 0)} / {week.get('limit_messages', 0)})")

    if openai:
        lines.append("")
        lines.append("🟢 ChatGPT Plus")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        if openai.get("available"):
            lines.append(f"   primary   {openai.get('primary_pct', 0):.1f}%")
            lines.append(f"   review    {openai.get('review_pct', 0):.1f}%")
        else:
            lines.append(f"   unavailable: {openai.get('error', 'unknown')}")

    return "\n".join(lines)
