from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from . import cache
from . import config as cfg_mod
from .claude import aggregator, limits as limits_mod, reader
from .formatters import detail, json_out, statusbar


def _build_summary(cfg) -> tuple[dict, dict | None]:
    cached = cache.read(cfg.cache_ttl_seconds)
    if cached is not None:
        return cached.get("summary", {}), cached.get("openai")

    entries = reader.load_entries()
    plan_limits = limits_mod.get_limits(cfg.plan, cfg.limits_override)
    summary = aggregator.summarize(entries, plan_limits)

    openai_data = None
    if cfg.openai_enabled:
        from .openai_chat.chatgpt_wham import fetch_chatgpt

        usage = fetch_chatgpt(cfg.openai_browser)
        openai_data = asdict(usage)

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
        print("🤖 err", end="")
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
