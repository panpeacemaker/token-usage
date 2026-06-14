from __future__ import annotations

import argparse
import contextlib
import sys
import time
import traceback
from dataclasses import asdict, replace

from . import _normalize, cache
from . import config as cfg_mod
from .claude import authoritative as authoritative_mod
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
        primary_limit_tokens=cfg.opencode_primary_limit_tokens,
        weekly_limit_tokens=cfg.opencode_weekly_limit_tokens,
        monthly_limit_tokens=cfg.opencode_monthly_limit_tokens,
    )
    return _normalize.normalize_windows(asdict(result), _normalize.OPENCODE_WINDOW_FIELDS)


def _fetch_opencode_go(cfg: cfg_mod.Config) -> dict | None:
    if not cfg.opencode_go_enabled:
        return None
    from pathlib import Path

    from .opencode.usage import DEFAULT_DB_PATH, fetch_opencode

    db_path = Path(cfg.opencode_go_db_path) if cfg.opencode_go_db_path else DEFAULT_DB_PATH
    result = fetch_opencode(
        provider_id=cfg.opencode_go_provider_id,
        db_path=db_path,
        primary_limit_tokens=cfg.opencode_go_primary_limit_tokens,
        weekly_limit_tokens=cfg.opencode_go_weekly_limit_tokens,
        monthly_limit_tokens=cfg.opencode_go_monthly_limit_tokens,
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
        cache_read_weight=cfg.claude_cache_read_weight,
    )
    statusline_usage = statusline.read_statusline_usage()
    return local_usage, local_detail, statusline_usage


def _statusline_mtime() -> float | None:
    try:
        return statusline.STATUSLINE_CACHE_FILE.stat().st_mtime
    except OSError:
        return None


def _lkg_window_validity(usage: ClaudeUsage, now: float) -> dict[str, bool]:
    """LKG windows are valid only when a future reset timestamp is known."""
    return {
        "five_valid": usage.five_hour_resets_at is not None and usage.five_hour_resets_at.timestamp() > now,
        "seven_valid": usage.seven_day_resets_at is not None and usage.seven_day_resets_at.timestamp() > now,
    }


def _select_claude_source(
    statusline_usage: ClaudeUsage | None,
    local_usage: ClaudeUsage,
) -> tuple[ClaudeUsage, str, str | None, dict]:
    """Pick the Claude source by trust, recording explicit provenance.

    Precedence (authoritative real numbers always beat the local JSONL estimate,
    because Anthropic's 5h/7d percentages are opaque and the cache-read-weighted
    local aggregation can be several times off — see the dashboard vs local gap):
      1. OAuth success     — official numbers (saved as last-known-good)
      2. Fresh statusline  — file <600s old + >=1 valid window (saved as LKG)
      3. LKG (valid)       — last real OAuth/statusline reading, windows unexpired;
                             real but slightly old → marked stale
      4. Local JSONL       — rough fallback ESTIMATE only when no real source is
                             available; marked estimate so it is never mistaken for
                             an authoritative number
      5. Stale statusline  — expired statusline as last resort, marked stale
      6. None              — nothing usable (available=False, error)
    """
    rejected: list[dict] = []
    sl_mtime = _statusline_mtime()
    statusline_age_s = time.time() - sl_mtime if sl_mtime is not None else None

    oauth_result = oauth_usage.fetch_usage()
    if oauth_result.available:
        authoritative_mod.save(oauth_result, "oauth")
        return oauth_result, "oauth", None, {
            "chosen": "oauth",
            "rejected": rejected,
            "statusline_age_s": statusline_age_s,
        }
    oauth_error = oauth_result.error or "unknown error"
    rejected.append({"source": "oauth", "reason": oauth_error})

    if statusline_usage is not None:
        valid, reason = statusline.check_validity(statusline_usage, file_mtime=sl_mtime)
        if valid:
            wv = statusline.window_validity(statusline_usage, file_mtime=sl_mtime)
            modified = statusline_usage
            if not wv["five_valid"]:
                modified = replace(modified, five_hour_pct=0.0, five_hour_resets_at=None)
            if not wv["seven_valid"]:
                modified = replace(modified, seven_day_pct=0.0, seven_day_resets_at=None)
            authoritative_mod.save(modified, "statusline")
            return modified, "statusline", None, {
                "chosen": "statusline",
                "rejected": rejected,
                "statusline_age_s": statusline_age_s,
                "_five_hour_expired": not wv["five_valid"],
                "_seven_day_expired": not wv["seven_valid"],
            }
        rejected.append({"source": "statusline", "reason": reason})
    else:
        rejected.append({"source": "statusline", "reason": "file missing"})

    lkg = authoritative_mod.load()
    if lkg is not None:
        lkg_usage, lkg_source, lkg_saved_at = lkg
        wv = _lkg_window_validity(lkg_usage, time.time())
        if wv["five_valid"] or wv["seven_valid"]:
            return lkg_usage, "lkg", oauth_error, {
                "chosen": "lkg",
                "rejected": rejected,
                "statusline_age_s": statusline_age_s,
                "_lkg_source": lkg_source,
                "_lkg_saved_at": lkg_saved_at,
                "_five_hour_estimate": not wv["five_valid"],
                "_seven_day_estimate": not wv["seven_valid"],
            }
        rejected.append({"source": "lkg", "reason": "window expired"})
    else:
        rejected.append({"source": "lkg", "reason": "no stored authoritative data"})

    if local_usage.available:
        return local_usage, "local", oauth_error, {
            "chosen": "local",
            "rejected": rejected,
            "statusline_age_s": statusline_age_s,
            "_five_hour_estimate": True,
            "_seven_day_estimate": True,
        }
    rejected.append({"source": "local", "reason": local_usage.error or "unavailable"})

    if statusline_usage is not None:
        return statusline_usage, "statusline-stale", oauth_error, {
            "chosen": "statusline-stale",
            "rejected": rejected,
            "statusline_age_s": statusline_age_s,
        }
    return (
        ClaudeUsage(
            available=False,
            error=f"oauth: {oauth_error}; no statusline or local fallback",
        ),
        "none",
        oauth_error,
        {
            "chosen": "none",
            "rejected": rejected,
            "statusline_age_s": statusline_age_s,
        },
    )


def _assemble_summary(
    claude_usage: ClaudeUsage,
    source: str,
    oauth_error: str | None,
    local_detail: dict,
    source_detail: dict,
) -> dict:
    summary = asdict(claude_usage)
    summary["_source"] = source
    summary["local"] = local_detail
    summary["_source_detail"] = source_detail

    if source_detail.get("_five_hour_expired"):
        summary["_five_hour_expired"] = True
    if source_detail.get("_seven_day_expired"):
        summary["_seven_day_expired"] = True

    if source_detail.get("_five_hour_estimate"):
        summary["_five_hour_estimate"] = True
    if source_detail.get("_seven_day_estimate"):
        summary["_seven_day_estimate"] = True

    if source == "statusline-stale":
        summary["_stale"] = True
        summary["_stale_reason"] = f"oauth failed ({oauth_error}); no local data; using expired statusline"
        with contextlib.suppress(OSError):
            summary["_fetched_at"] = statusline.STATUSLINE_CACHE_FILE.stat().st_mtime

    if source == "lkg":
        summary["_stale"] = True
        age = "unknown"
        saved_at = source_detail.get("_lkg_saved_at")
        if saved_at is not None:
            summary["_fetched_at"] = float(saved_at)
            age = f"{int(time.time() - float(saved_at))}s"
        summary["_stale_reason"] = f"oauth failed ({oauth_error}); using last-known-good authoritative data ({age} old)"

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
            claude_usage, source, oauth_error, source_detail = _select_claude_source(statusline_usage, local_usage)
            summary = _assemble_summary(claude_usage, source, oauth_error, local_detail, source_detail)
            fetched.add("claude")
    else:
        summary = existing.get("summary") or _empty_claude_summary()

    if "chatgpt" in fetchable:
        if cache.is_provider_fresh(existing, "chatgpt", ttl) and _cache_has_provider(existing, "chatgpt"):
            openai_data = _normalize.normalize_windows(existing.get("openai"), _normalize.OPENAI_WINDOW_FIELDS)
        else:
            openai_data = _fetch_openai(cfg)
            fetched.add("chatgpt")
    elif "chatgpt" in selected:
        openai_data = _normalize.normalize_windows(existing.get("openai"), _normalize.OPENAI_WINDOW_FIELDS)
    else:
        openai_data = existing.get("openai")

    if "kimi" in fetchable:
        if cache.is_provider_fresh(existing, "kimi", ttl) and _cache_has_provider(existing, "kimi"):
            kimi_data = _normalize.normalize_windows(existing.get("kimi"), _normalize.KIMI_WINDOW_FIELDS)
        else:
            kimi_data = _fetch_kimi(cfg)
            fetched.add("kimi")
    elif "kimi" in selected:
        kimi_data = _normalize.normalize_windows(existing.get("kimi"), _normalize.KIMI_WINDOW_FIELDS)
    else:
        kimi_data = existing.get("kimi")

    if "opencode" in fetchable:
        if cache.is_provider_fresh(existing, "opencode", ttl) and _cache_has_provider(existing, "opencode"):
            opencode_data = _normalize.normalize_windows(
                existing.get("opencode"), _normalize.OPENCODE_WINDOW_FIELDS
            )
        else:
            opencode_data = _fetch_opencode(cfg)
            fetched.add("opencode")
    elif "opencode" in selected:
        opencode_data = _normalize.normalize_windows(
            existing.get("opencode"), _normalize.OPENCODE_WINDOW_FIELDS
        )
    else:
        opencode_data = existing.get("opencode")

    if "opencode-go" in fetchable:
        if cache.is_provider_fresh(existing, "opencode-go", ttl) and _cache_has_provider(existing, "opencode-go"):
            opencode_go_data = _normalize.normalize_windows(
                existing.get("opencode_go"), _normalize.OPENCODE_WINDOW_FIELDS
            )
        else:
            opencode_go_data = _fetch_opencode_go(cfg)
            fetched.add("opencode-go")
    elif "opencode-go" in selected:
        opencode_go_data = _normalize.normalize_windows(
            existing.get("opencode_go"), _normalize.OPENCODE_WINDOW_FIELDS
        )
    else:
        opencode_go_data = existing.get("opencode_go")

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
        traceback.print_exc(file=sys.stderr)
        print("c err", end="")
        return 1

    sel = set(providers)
    summary_for_render = summary if "claude" in sel else None
    openai_for_render = openai_data if "chatgpt" in sel else None
    kimi_for_render = kimi_data if "kimi" in sel else None
    opencode_for_render = opencode_data if "opencode" in sel else None
    opencode_go_for_render = opencode_go_data if "opencode-go" in sel else None

    bar_windows = {
        "claude": cfg.claude_bar_window,
        "openai": cfg.openai_bar_window,
        "kimi": cfg.kimi_bar_window,
        "opencode": cfg.opencode_bar_window,
        "opencode-go": cfg.opencode_go_bar_window,
    }

    if args.detail:
        print(
            detail.format_detail(
                summary_for_render,
                openai_for_render,
                kimi_for_render,
                opencode_for_render,
                opencode_go_for_render,
                bar_windows=bar_windows,
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
                bar_windows=bar_windows,
            ),
            end="",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
