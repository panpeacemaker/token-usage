from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict

from . import cache
from . import config as cfg_mod
from .claude import aggregator, limits as limits_mod, reader
from .claude.oauth_usage import fetch_usage as fetch_claude_usage
from .formatters import detail, json_out, statusbar


def _fetch_local(plan: str, overrides: dict) -> dict:
    try:
        entries = reader.load_entries()
        plan_limits = limits_mod.get_limits(plan, overrides)
        local_summary = aggregator.summarize(entries, plan_limits)
        return {
            "active_block": local_summary.get("active_block"),
            "week": local_summary.get("week"),
            "total_entries": local_summary.get("total_entries"),
        }
    except Exception as e:
        return {"error": str(e)}


def _fetch_openai(cfg) -> dict | None:
    if not cfg.openai_enabled:
        return None
    from .openai_chat.chatgpt_wham import fetch_chatgpt

    return asdict(fetch_chatgpt(cfg.openai_browser))


def _build_summary(cfg) -> tuple[dict, dict | None]:
    cached_raw = cache.read_raw()
    now = time.time()

    fresh_cache = cache.read(cfg.cache_ttl_seconds)
    if fresh_cache is not None:
        return fresh_cache.get("summary", {}), fresh_cache.get("openai")

    if cached_raw is not None and now < cached_raw.get("next_retry_at", 0):
        cached_summary = cached_raw.get("summary") or {}
        cached_openai = cached_raw.get("openai")
        openai_data = cached_openai if cached_openai is not None else _fetch_openai(cfg)

        if cached_summary:
            stale_summary = dict(cached_summary)
            stale_summary["_stale"] = True
            stale_summary["_stale_reason"] = "rate-limit backoff"
            stale_summary["_retry_at"] = cached_raw.get("next_retry_at")
            stale_summary["_fetched_at"] = cached_raw.get("fetched_at")
            return stale_summary, openai_data
        return {
            "available": False,
            "error": "rate-limit backoff",
            "_retry_at": cached_raw.get("next_retry_at"),
            "_stale": False,
        }, openai_data

    claude_usage = fetch_claude_usage()

    if claude_usage.available:
        summary = asdict(claude_usage)
        summary["local"] = _fetch_local(cfg.plan, cfg.limits_override)
        openai_data = _fetch_openai(cfg)
        cache.write({"summary": summary, "openai": openai_data})
        return summary, openai_data

    is_rate_limited = "429" in (claude_usage.error or "")
    min_backoff = 120 if is_rate_limited else 0

    if cached_raw is not None:
        cache_age = now - cached_raw.get("fetched_at", 0)
        if cache_age <= cfg.stale_fallback_max_age_seconds:
            stale_summary = dict(cached_raw.get("summary") or {})
            stale_summary["_stale"] = True
            stale_summary["_stale_reason"] = claude_usage.error or "fetch failed"
            stale_summary["_fetched_at"] = cached_raw.get("fetched_at")

            backoff_seconds = max(claude_usage.retry_after_seconds or 0, min_backoff)
            if backoff_seconds > 0:
                retry_at = now + backoff_seconds
                stale_summary["_retry_at"] = retry_at
                cache.update_retry_at(retry_at)

            return stale_summary, cached_raw.get("openai")

    backoff_seconds = max(claude_usage.retry_after_seconds or 0, min_backoff)
    if backoff_seconds > 0:
        cache.write_cooldown_only(now + backoff_seconds)

    summary = asdict(claude_usage)
    summary["local"] = None
    openai_data = _fetch_openai(cfg)
    return summary, openai_data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="token-usage")
    sub = ap.add_mutually_exclusive_group()
    sub.add_argument("--statusbar", action="store_true", help="Compact statusbar string (default)")
    sub.add_argument("--detail", action="store_true", help="Multi-line detail for notifications")
    sub.add_argument("--json", action="store_true", help="Raw JSON")
    ap.add_argument("--no-cache", action="store_true", help="Bypass cache")
    args = ap.parse_args(argv)

    cfg = cfg_mod.load()
    if args.no_cache:
        cfg.cache_ttl_seconds = 0

    try:
        summary, openai_data = _build_summary(cfg)
    except Exception as e:
        print(f"err: {e}", file=sys.stderr)
        print("| C err ", end="")
        return 1

    if args.detail:
        print(detail.format_detail(summary, openai_data))
    elif args.json:
        print(json_out.format_json(summary, openai_data))
    else:
        print(statusbar.format_compact(summary, openai_data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
