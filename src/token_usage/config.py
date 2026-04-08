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


@dataclass
class Config:
    plan: str = "max20"
    limits_override: dict = field(default_factory=dict)
    openai_enabled: bool = True
    openai_browser: str = "zen"
    cache_ttl_seconds: int = 90


def load() -> Config:
    if not CONFIG_FILE.exists():
        return Config()
    try:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return Config()
    claude = data.get("claude") or {}
    openai_cfg = data.get("openai") or {}
    cache_cfg = data.get("cache") or {}
    return Config(
        plan=claude.get("plan", "max20"),
        limits_override=claude.get("limits", {}) or {},
        openai_enabled=bool(openai_cfg.get("enabled", True)),
        openai_browser=openai_cfg.get("browser", "zen"),
        cache_ttl_seconds=int(cache_cfg.get("ttl_seconds", 90)),
    )
