from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from . import cache
from . import config as cfg_mod
from .claude import limits as limits_mod, local_summary, oauth_usage, statusline
from .claude.models import ClaudeUsage
from .formatters import detail, json_out, statusbar


def _fetch_openai(cfg: cfg_mod.Config) -> dict | None:
    if not cfg.openai_enabled:
        return None
    from .openai_chat.chatgpt_wham import fetch_chatgpt

    return asdict(fetch_chatgpt(cfg.openai_browser))


def _build_summary(cfg: cfg_mod.Config) -> tuple[dict, dict | None]:
    fresh_cache = cache.read(cfg.cache_ttl_seconds)
    if fresh_cache is not None:
        return fresh_cache.get("summary", {}), fresh_cache.get("openai")

    plan_limits = limits_mod.get_limits(cfg.plan, cfg.limits_override)
    local_usage, local_detail = local_summary.compute_local(
        plan_limits,
        weekly_reset_weekday=cfg.weekly_reset_weekday,
        weekly_reset_hour_local=cfg.weekly_reset_hour_local,
    )
    statusline_usage = statusline.read_statusline_usage()

    claude_usage: ClaudeUsage
    source: str
    oauth_error: str | None = None
    if statusline_usage is not None and statusline.is_still_valid(statusline_usage):
        claude_usage = statusline_usage
        source = "statusline"
    else:
        oauth_result = oauth_usage.fetch_usage()
        if oauth_result.available:
            claude_usage = oauth_result
            source = "oauth"
        else:
            oauth_error = oauth_result.error
            if local_usage.available:
                claude_usage = local_usage
                source = "local"
            elif statusline_usage is not None:
                claude_usage = statusline_usage
                source = "statusline-stale"
            else:
                claude_usage = ClaudeUsage(
                    available=False,
                    error=f"oauth: {oauth_error}; no statusline or local fallback",
                )
                source = "none"

    summary = asdict(claude_usage)
    summary["_source"] = source
    summary["local"] = local_detail

    openai_data = _fetch_openai(cfg)
    cache.write({"summary": summary, "openai": openai_data})
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
