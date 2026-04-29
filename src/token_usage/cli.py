from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from . import _normalize, cache
from . import config as cfg_mod
from .claude import limits as limits_mod
from .claude import local_summary, oauth_usage, statusline
from .claude.models import ClaudeUsage
from .formatters import detail, json_out, statusbar


def _fetch_openai(cfg: cfg_mod.Config) -> dict | None:
    if not cfg.openai_enabled:
        return None
    from .openai_chat.chatgpt_wham import fetch_chatgpt

    return _normalize.normalize_windows(asdict(fetch_chatgpt(cfg.openai_browser)), _normalize.OPENAI_WINDOW_FIELDS)


def _fetch_kimi(cfg: cfg_mod.Config) -> dict | None:
    if not cfg.kimi_enabled:
        return None
    from .kimi.usage import fetch_kimi

    return _normalize.normalize_windows(asdict(fetch_kimi(cfg.kimi_browser)), _normalize.KIMI_WINDOW_FIELDS)


def _fetch_opencode(cfg: cfg_mod.Config) -> dict | None:
    if not cfg.opencode_enabled:
        return None
    from pathlib import Path

    from .opencode.usage import DEFAULT_DB_PATH, fetch_opencode

    db_path = Path(cfg.opencode_db_path) if cfg.opencode_db_path else DEFAULT_DB_PATH
    result = fetch_opencode(
        provider_id=cfg.opencode_provider_id,
        db_path=db_path,
        primary_window_hours=cfg.opencode_primary_window_hours,
        weekly_window_days=cfg.opencode_weekly_window_days,
        primary_limit_tokens=cfg.opencode_primary_limit_tokens,
        weekly_limit_tokens=cfg.opencode_weekly_limit_tokens,
    )
    return _normalize.normalize_windows(asdict(result), _normalize.OPENCODE_WINDOW_FIELDS)


def _fetch_opencode_go(cfg: cfg_mod.Config) -> dict | None:
    if not cfg.opencode_go_enabled:
        return None
    from pathlib import Path

    from .opencode.usage import DEFAULT_DB_PATH, fetch_opencode

    db_path = Path(cfg.opencode_db_path) if cfg.opencode_db_path else DEFAULT_DB_PATH
    result = fetch_opencode(
        provider_id="opencode-go",
        db_path=db_path,
        primary_window_hours=cfg.opencode_go_primary_window_hours,
        weekly_window_days=cfg.opencode_go_weekly_window_days,
        primary_limit_tokens=cfg.opencode_go_primary_limit_tokens,
        weekly_limit_tokens=cfg.opencode_go_weekly_limit_tokens,
    )
    return _normalize.normalize_windows(asdict(result), _normalize.OPENCODE_WINDOW_FIELDS)


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
    if name == "opencode":
        return payload.get("opencode") is not None
    if name == "opencode-go":
        return payload.get("opencode_go") is not None
    return False


def _providers_to_actually_fetch(cfg: cfg_mod.Config, selected: set[str]) -> set[str]:
    fetched = set()
    if "claude" in selected:
        fetched.add("claude")
    if "chatgpt" in selected and cfg.openai_enabled:
        fetched.add("chatgpt")
    if "kimi" in selected and cfg.kimi_enabled:
        fetched.add("kimi")
    if "opencode" in selected and cfg.opencode_enabled:
        fetched.add("opencode")
    if "opencode-go" in selected and cfg.opencode_go_enabled:
        fetched.add("opencode-go")
    return fetched


def _build_summary(
    cfg: cfg_mod.Config, providers: tuple[str, ...] | None = None
) -> tuple[dict, dict | None, dict | None, dict | None, dict | None]:
    selected = set(providers) if providers else set(cfg_mod.ALL_PROVIDERS)
    fetchable = _providers_to_actually_fetch(cfg, selected)
    ttl = cfg.cache_ttl_seconds

    existing = cache.read_raw() or {}
    fetched: set[str] = set()

    if "claude" in selected:
        if cache.is_provider_fresh(existing, "claude", ttl) and _cache_has_provider(existing, "claude"):
            summary = existing.get("summary", {})
        else:
            local_usage, local_detail, statusline_usage = _gather_sources(cfg)
            claude_usage, source, oauth_error = _select_claude_source(statusline_usage, local_usage)
            summary = _assemble_summary(claude_usage, source, oauth_error, local_detail)
            fetched.add("claude")
    else:
        summary = existing.get("summary") or _empty_claude_summary()

    if "chatgpt" in fetchable:
        if cache.is_provider_fresh(existing, "chatgpt", ttl) and _cache_has_provider(existing, "chatgpt"):
            openai_data = _normalize.normalize_windows(existing.get("openai"), _normalize.OPENAI_WINDOW_FIELDS)
        else:
            openai_data = _fetch_openai(cfg)
            fetched.add("chatgpt")
    else:
        openai_data = _normalize.normalize_windows(existing.get("openai"), _normalize.OPENAI_WINDOW_FIELDS)

    if "kimi" in fetchable:
        if cache.is_provider_fresh(existing, "kimi", ttl) and _cache_has_provider(existing, "kimi"):
            kimi_data = _normalize.normalize_windows(existing.get("kimi"), _normalize.KIMI_WINDOW_FIELDS)
        else:
            kimi_data = _fetch_kimi(cfg)
            fetched.add("kimi")
    else:
        kimi_data = _normalize.normalize_windows(existing.get("kimi"), _normalize.KIMI_WINDOW_FIELDS)

    if "opencode" in fetchable:
        if cache.is_provider_fresh(existing, "opencode", ttl) and _cache_has_provider(existing, "opencode"):
            opencode_data = _normalize.normalize_windows(
                existing.get("opencode"), _normalize.OPENCODE_WINDOW_FIELDS
            )
        else:
            opencode_data = _fetch_opencode(cfg)
            fetched.add("opencode")
    else:
        opencode_data = _normalize.normalize_windows(
            existing.get("opencode"), _normalize.OPENCODE_WINDOW_FIELDS
        )

    if "opencode-go" in fetchable:
        if cache.is_provider_fresh(existing, "opencode-go", ttl) and _cache_has_provider(existing, "opencode-go"):
            opencode_go_data = _normalize.normalize_windows(
                existing.get("opencode_go"), _normalize.OPENCODE_WINDOW_FIELDS
            )
        else:
            opencode_go_data = _fetch_opencode_go(cfg)
            fetched.add("opencode-go")
    else:
        opencode_go_data = _normalize.normalize_windows(
            existing.get("opencode_go"), _normalize.OPENCODE_WINDOW_FIELDS
        )

    cache.write(
        {
            "summary": summary,
            "openai": openai_data,
            "kimi": kimi_data,
            "opencode": opencode_data,
            "opencode_go": opencode_go_data,
        },
        fetched_providers=fetched,
    )
    return summary, openai_data, kimi_data, opencode_data, opencode_go_data


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
        summary, openai_data, kimi_data, opencode_data, opencode_go_data = _build_summary(cfg, providers)
    except Exception as e:
        print(f"err: {type(e).__name__}: {e}", file=sys.stderr)
        print("c err", end="")
        return 1

    sel = set(providers)
    summary_for_render = summary if "claude" in sel else None
    openai_for_render = openai_data if "chatgpt" in sel else None
    kimi_for_render = kimi_data if "kimi" in sel else None
    opencode_for_render = opencode_data if "opencode" in sel else None
    opencode_go_for_render = opencode_go_data if "opencode-go" in sel else None

    if args.detail:
        print(
            detail.format_detail(
                summary_for_render,
                openai_for_render,
                kimi_for_render,
                opencode_for_render,
                opencode_go_for_render,
            )
        )
    elif args.json:
        print(
            json_out.format_json(
                summary_for_render or {},
                openai_for_render,
                kimi_for_render,
                opencode_for_render,
                opencode_go_for_render,
            )
        )
    else:
        bare = user_supplied_only and len(providers) == 1
        print(
            statusbar.format_compact(
                summary_for_render or {},
                openai_for_render,
                kimi_for_render,
                opencode_for_render,
                opencode_go_for_render,
                bare=bare,
            ),
            end="",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
