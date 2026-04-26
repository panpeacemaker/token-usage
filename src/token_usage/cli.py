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


def _fetch_kimi(cfg: cfg_mod.Config) -> dict | None:
    if not cfg.kimi_enabled:
        return None
    from .kimi.usage import fetch_kimi

    return asdict(fetch_kimi(cfg.kimi_browser))


def _gather_sources(
    cfg: cfg_mod.Config,
) -> tuple[ClaudeUsage, dict, ClaudeUsage | None]:
    plan_limits = limits_mod.get_limits(cfg.plan, cfg.limits_override)
    local_usage, local_detail = local_summary.compute_local(
        plan_limits,
        weekly_reset_weekday=cfg.weekly_reset_weekday,
        weekly_reset_hour_local=cfg.weekly_reset_hour_local,
    )
    statusline_usage = statusline.read_statusline_usage()
    return local_usage, local_detail, statusline_usage


def _statusline_mtime() -> float | None:
    try:
        return statusline.STATUSLINE_CACHE_FILE.stat().st_mtime
    except OSError:
        return None


def _select_claude_source(
    statusline_usage: ClaudeUsage | None,
    local_usage: ClaudeUsage,
) -> tuple[ClaudeUsage, str, str | None]:
    sl_mtime = _statusline_mtime()
    if statusline_usage is not None and statusline.is_still_valid(statusline_usage, file_mtime=sl_mtime):
        return statusline_usage, "statusline", None

    oauth_result = oauth_usage.fetch_usage()
    if oauth_result.available:
        return oauth_result, "oauth", None

    oauth_error = oauth_result.error
    if local_usage.available:
        return local_usage, "local", oauth_error
    if statusline_usage is not None:
        return statusline_usage, "statusline-stale", oauth_error
    return (
        ClaudeUsage(
            available=False,
            error=f"oauth: {oauth_error}; no statusline or local fallback",
        ),
        "none",
        oauth_error,
    )


def _assemble_summary(
    claude_usage: ClaudeUsage,
    source: str,
    oauth_error: str | None,
    local_detail: dict,
) -> dict:
    summary = asdict(claude_usage)
    summary["_source"] = source
    summary["local"] = local_detail

    if source == "statusline-stale":
        summary["_stale"] = True
        summary["_stale_reason"] = f"oauth failed ({oauth_error}); no local data; using expired statusline"
        try:
            summary["_fetched_at"] = statusline.STATUSLINE_CACHE_FILE.stat().st_mtime
        except OSError:
            pass

    return summary


def _empty_claude_summary() -> dict:
    return {"available": False, "error": "skipped (--only filter)", "_source": "skipped", "local": {}}


def _cache_has_provider(payload: dict | None, name: str) -> bool:
    if not payload:
        return False
    if name == "claude":
        s = payload.get("summary") or {}
        return bool(s) and s.get("_source") not in (None, "skipped")
    if name == "chatgpt":
        return payload.get("openai") is not None
    if name == "kimi":
        return payload.get("kimi") is not None
    return False


def _providers_to_actually_fetch(cfg: cfg_mod.Config, selected: set[str]) -> set[str]:
    fetched = set()
    if "claude" in selected:
        fetched.add("claude")
    if "chatgpt" in selected and cfg.openai_enabled:
        fetched.add("chatgpt")
    if "kimi" in selected and cfg.kimi_enabled:
        fetched.add("kimi")
    return fetched


def _build_summary(
    cfg: cfg_mod.Config, providers: tuple[str, ...] | None = None
) -> tuple[dict, dict | None, dict | None]:
    selected = set(providers) if providers else set(cfg_mod.ALL_PROVIDERS)
    fetched = _providers_to_actually_fetch(cfg, selected)
    fresh_cache = cache.read(cfg.cache_ttl_seconds)
    if fresh_cache is not None and all(_cache_has_provider(fresh_cache, p) for p in fetched):
        return (
            fresh_cache.get("summary", {}),
            fresh_cache.get("openai"),
            fresh_cache.get("kimi"),
        )

    existing = fresh_cache or cache.read_raw() or {}

    if "claude" in selected:
        local_usage, local_detail, statusline_usage = _gather_sources(cfg)
        claude_usage, source, oauth_error = _select_claude_source(statusline_usage, local_usage)
        summary = _assemble_summary(claude_usage, source, oauth_error, local_detail)
    else:
        summary = existing.get("summary") or _empty_claude_summary()

    openai_data = _fetch_openai(cfg) if "chatgpt" in selected else existing.get("openai")
    kimi_data = _fetch_kimi(cfg) if "kimi" in selected else existing.get("kimi")
    cache.write({"summary": summary, "openai": openai_data, "kimi": kimi_data})
    return summary, openai_data, kimi_data


def main(argv: list[str] | None = None) -> int:
    from . import __version__

    ap = argparse.ArgumentParser(prog="token-usage")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_mutually_exclusive_group()
    sub.add_argument("--statusbar", action="store_true", help="Compact statusbar string (default)")
    sub.add_argument("--detail", action="store_true", help="Multi-line detail for notifications")
    sub.add_argument("--json", action="store_true", help="Raw JSON")
    ap.add_argument("--no-cache", action="store_true", help="Bypass cache")
    ap.add_argument(
        "--only",
        metavar="PROVIDER[,PROVIDER...]",
        help="Restrict to a subset of providers (claude, chatgpt, kimi). Skips fetch+render for the rest.",
    )
    args = ap.parse_args(argv)

    cfg = cfg_mod.load()
    if args.no_cache:
        cfg.cache_ttl_seconds = 0

    if args.only is not None:
        providers = cfg_mod._normalize_providers(args.only)
        user_supplied_only = True
    else:
        providers = cfg.statusbar_providers
        user_supplied_only = False

    try:
        summary, openai_data, kimi_data = _build_summary(cfg, providers)
    except Exception as e:
        print(f"err: {type(e).__name__}: {e}", file=sys.stderr)
        print("c err", end="")
        return 1

    sel = set(providers)
    summary_for_render = summary if "claude" in sel else None
    openai_for_render = openai_data if "chatgpt" in sel else None
    kimi_for_render = kimi_data if "kimi" in sel else None

    if args.detail:
        print(detail.format_detail(summary_for_render or {}, openai_for_render, kimi_for_render))
    elif args.json:
        print(json_out.format_json(summary_for_render or {}, openai_for_render, kimi_for_render))
    else:
        bare = user_supplied_only and len(providers) == 1
        print(
            statusbar.format_compact(
                summary_for_render or {},
                openai_for_render,
                kimi_for_render,
                bare=bare,
            ),
            end="",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
