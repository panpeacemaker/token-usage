from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = importlib.import_module("tomli")

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "token-usage"
CONFIG_FILE = CONFIG_DIR / "config.toml"


ALL_PROVIDERS = ("claude", "chatgpt", "kimi", "opencode", "opencode-go")


@dataclass
class Config:
    plan: str = "max5"
    limits_override: dict = field(default_factory=dict)
    openai_enabled: bool = True
    openai_browser: str = "zen"
    kimi_enabled: bool = True
    kimi_browser: str = "zen"
    opencode_enabled: bool = False
    opencode_provider_id: str = "opencode"
    opencode_db_path: str = ""
    opencode_primary_window_hours: int = 5
    opencode_weekly_window_days: int = 7
    opencode_primary_limit_tokens: int = 0
    opencode_weekly_limit_tokens: int = 0
    opencode_go_enabled: bool = False
    opencode_go_primary_window_hours: int = 5
    opencode_go_weekly_window_days: int = 7
    opencode_go_primary_limit_tokens: int = 0
    opencode_go_weekly_limit_tokens: int = 0
    cache_ttl_seconds: int = 300
    weekly_reset_weekday: int = 0
    weekly_reset_hour_local: int = 22
    statusbar_providers: tuple[str, ...] = ALL_PROVIDERS


def load() -> Config:
    if not CONFIG_FILE.exists():
        return Config()
    try:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        import sys

        print(f"warn: config load failed ({CONFIG_FILE}): {e}", file=sys.stderr)
        return Config()
    claude = data.get("claude") or {}
    openai_cfg = data.get("openai") or {}
    kimi_cfg = data.get("kimi") or {}
    opencode_cfg = data.get("opencode") or {}
    opencode_go_cfg = data.get("opencode-go") or {}
    cache_cfg = data.get("cache") or {}
    statusbar_cfg = data.get("statusbar") or {}
    raw_providers = statusbar_cfg.get("providers")
    providers = _normalize_providers(raw_providers) if raw_providers is not None else ALL_PROVIDERS
    return Config(
        plan=claude.get("plan", "max5"),
        limits_override=claude.get("limits", {}) or {},
        openai_enabled=bool(openai_cfg.get("enabled", True)),
        openai_browser=openai_cfg.get("browser", "zen"),
        kimi_enabled=bool(kimi_cfg.get("enabled", True)),
        kimi_browser=kimi_cfg.get("browser", "zen"),
        opencode_enabled=bool(opencode_cfg.get("enabled", False)),
        opencode_provider_id=str(opencode_cfg.get("provider_id", "opencode")),
        opencode_db_path=str(opencode_cfg.get("db_path", "") or ""),
        opencode_primary_window_hours=int(opencode_cfg.get("primary_window_hours", 5)),
        opencode_weekly_window_days=int(opencode_cfg.get("weekly_window_days", 7)),
        opencode_primary_limit_tokens=int(opencode_cfg.get("primary_limit_tokens", 0)),
        opencode_weekly_limit_tokens=int(opencode_cfg.get("weekly_limit_tokens", 0)),
        opencode_go_enabled=bool(opencode_go_cfg.get("enabled", False)),
        opencode_go_primary_window_hours=int(opencode_go_cfg.get("primary_window_hours", 5)),
        opencode_go_weekly_window_days=int(opencode_go_cfg.get("weekly_window_days", 7)),
        opencode_go_primary_limit_tokens=int(opencode_go_cfg.get("primary_limit_tokens", 0)),
        opencode_go_weekly_limit_tokens=int(opencode_go_cfg.get("weekly_limit_tokens", 0)),
        cache_ttl_seconds=int(cache_cfg.get("ttl_seconds", 300)),
        weekly_reset_weekday=int(claude.get("weekly_reset_weekday", 0)),
        weekly_reset_hour_local=int(claude.get("weekly_reset_hour_local", 22)),
        statusbar_providers=providers,
    )


def _normalize_providers(raw) -> tuple[str, ...]:
    if isinstance(raw, str):
        items = [p.strip().lower() for p in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        items = [str(p).strip().lower() for p in raw]
    else:
        return ALL_PROVIDERS
    aliases = {
        "openai": "chatgpt",
        "gpt": "chatgpt",
        "c": "claude",
        "o": "chatgpt",
        "k": "kimi",
        "e": "opencode",
        "oc": "opencode",
        "zen": "opencode",
        "opencode-zen": "opencode",
        "g": "opencode-go",
        "oc-go": "opencode-go",
        "go": "opencode-go",
    }
    seen: list[str] = []
    for it in items:
        if not it:
            continue
        name = aliases.get(it, it)
        if name in ALL_PROVIDERS and name not in seen:
            seen.append(name)
    return tuple(seen) if seen else ALL_PROVIDERS
