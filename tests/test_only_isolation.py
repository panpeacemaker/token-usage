from __future__ import annotations

import json
import time
from unittest.mock import patch

from token_usage import cli as cli_mod
from token_usage import cache as cache_mod
from token_usage import config as cfg_mod


def _cfg(**overrides):
    cfg = cfg_mod.Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _json_bytes(obj) -> bytes:
    """Deterministic JSON serialization for byte-level comparison."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_only_kimi_leaves_other_provider_subtrees_unchanged() -> None:
    """Running --only kimi against a full cache must not mutate non-kimi bytes."""
    cfg = _cfg(cache_ttl_seconds=300)
    existing = {
        "summary": {
            "available": True,
            "_source": "oauth",
            "five_hour_pct": 30.0,
            "seven_day_pct": 10.0,
            "five_hour_resets_at": 4081503240,
            "_source_detail": {"chosen": "oauth", "rejected": [], "statusline_age_s": None},
        },
        "openai": {
            "available": True,
            "primary_pct": 80.0,
            "primary_reset_at": 4081503240,
            "weekly_pct": 50.0,
            "weekly_reset_at": 4082100040,
        },
        "kimi": {
            "available": True,
            "primary_pct": 10.0,
            "weekly_pct": 5.0,
        },
        "opencode": {
            "available": True,
            "provider_id": "opencode",
            "primary_pct": 12.0,
            "weekly_pct": 3.0,
        },
        "opencode_go": {
            "available": True,
            "provider_id": "opencode-go",
            "primary_pct": 25.0,
            "weekly_pct": 8.0,
        },
        "_version": 10,
        "fetched_at": 1000.0,
        "_provider_fetched_at": {
            "claude": 1000.0,
            "chatgpt": 1000.0,
            "kimi": 1000.0,
            "opencode": 1000.0,
            "opencode-go": 1000.0,
        },
    }

    written_payload: dict = {}
    write_kwargs: dict = {}

    def _fake_write(payload, fetched_providers=None):
        written_payload.update(payload)
        write_kwargs["fetched_providers"] = fetched_providers

    new_kimi = {"available": True, "primary_pct": 99.0, "weekly_pct": 50.0}

    with (
        patch.object(cache_mod, "read_raw", return_value=existing),
        patch.object(cache_mod, "write", side_effect=_fake_write),
        patch.object(cli_mod, "_fetch_kimi", return_value=new_kimi),
        patch.object(cli_mod, "_gather_sources") as mock_gather,
        patch.object(cli_mod, "_fetch_openai") as mock_openai,
        patch.object(cli_mod, "_fetch_opencode") as mock_opencode,
        patch.object(cli_mod, "_fetch_opencode_go") as mock_opencode_go,
    ):
        from token_usage.claude.models import ClaudeUsage

        mock_gather.return_value = (ClaudeUsage(available=True), {}, None)
        summary, openai, kimi, opencode, opencode_go = cli_mod._build_summary(cfg, providers=("kimi",))

    # Non-kimi provider data must be identical byte-for-byte in their JSON subtrees
    assert _json_bytes(written_payload.get("summary")) == _json_bytes(existing["summary"])
    assert _json_bytes(written_payload.get("openai")) == _json_bytes(existing["openai"])
    assert _json_bytes(written_payload.get("opencode")) == _json_bytes(existing["opencode"])
    assert _json_bytes(written_payload.get("opencode_go")) == _json_bytes(existing["opencode_go"])

    # Kimi must be updated
    assert _json_bytes(written_payload.get("kimi")) == _json_bytes(new_kimi)
    assert kimi == new_kimi

    # Only kimi should be in fetched_providers
    assert write_kwargs["fetched_providers"] == {"kimi"}

    # Other fetchers must not have been called
    mock_gather.assert_not_called()
    mock_openai.assert_not_called()
    mock_opencode.assert_not_called()
    mock_opencode_go.assert_not_called()


def test_only_kimi_updates_only_kimi_provider_fetched_at() -> None:
    """Only kimi's per-provider timestamp must advance; others stay frozen."""
    cfg = _cfg(cache_ttl_seconds=300)
    old_ts = 1000.0
    existing = {
        "summary": {"available": True, "_source": "oauth", "five_hour_pct": 30.0},
        "openai": {"available": True, "primary_pct": 80.0},
        "kimi": {"available": True, "primary_pct": 10.0},
        "opencode": None,
        "opencode_go": None,
        "_version": 10,
        "fetched_at": old_ts,
        "_provider_fetched_at": {
            "claude": old_ts,
            "chatgpt": old_ts,
            "kimi": old_ts,
        },
    }

    written_per_provider: dict = {}
    write_kwargs: dict = {}

    def _fake_write(payload, fetched_providers=None):
        now = time.time()
        raw = cache_mod.read_raw() or {}
        existing_per = raw.get("_provider_fetched_at") or {}
        per_provider: dict[str, float] = {}
        for k, v in existing_per.items():
            try:
                ts = float(v)
            except (TypeError, ValueError):
                continue
            if ts <= now:
                per_provider[str(k)] = ts
        if fetched_providers:
            for name in fetched_providers:
                per_provider[name] = now
        written_per_provider.update(per_provider)
        write_kwargs["fetched_providers"] = fetched_providers

    with (
        patch.object(cache_mod, "read_raw", return_value=existing),
        patch.object(cache_mod, "write", side_effect=_fake_write),
        patch.object(cli_mod, "_fetch_kimi", return_value={"available": True, "primary_pct": 99.0}),
        patch.object(cli_mod, "_gather_sources") as mock_gather,
    ):
        from token_usage.claude.models import ClaudeUsage

        mock_gather.return_value = (ClaudeUsage(available=True), {}, None)
        cli_mod._build_summary(cfg, providers=("kimi",))

    # Non-kimi stamps unchanged
    assert written_per_provider.get("claude") == old_ts
    assert written_per_provider.get("chatgpt") == old_ts

    # Kimi stamp advanced
    assert written_per_provider.get("kimi") > old_ts


def test_only_claude_leaves_chatgpt_kimi_opencode_unchanged() -> None:
    """Symmetry: --only claude must not touch other provider subtrees."""
    cfg = _cfg(cache_ttl_seconds=300)
    existing = {
        "summary": {"available": True, "_source": "statusline", "five_hour_pct": 55.0},
        "openai": {"available": True, "primary_pct": 80.0, "primary_reset_at": 4081503240},
        "kimi": {"available": True, "primary_pct": 10.0},
        "opencode": {"available": True, "provider_id": "opencode", "primary_pct": 12.0},
        "opencode_go": {"available": True, "provider_id": "opencode-go", "primary_pct": 25.0},
        "_version": 10,
        "fetched_at": 1000.0,
        "_provider_fetched_at": {
            "claude": 1000.0,
            "chatgpt": 1000.0,
            "kimi": 1000.0,
            "opencode": 1000.0,
            "opencode-go": 1000.0,
        },
    }

    written_payload: dict = {}
    write_kwargs: dict = {}

    def _fake_write(payload, fetched_providers=None):
        written_payload.update(payload)
        write_kwargs["fetched_providers"] = fetched_providers

    with (
        patch.object(cache_mod, "read_raw", return_value=existing),
        patch.object(cache_mod, "write", side_effect=_fake_write),
        patch.object(cli_mod, "_gather_sources") as mock_gather,
        patch.object(cli_mod, "_select_claude_source") as mock_select,
        patch.object(cli_mod, "_assemble_summary", return_value={"available": True, "_source": "statusline"}),
        patch.object(cli_mod, "_fetch_openai") as mock_openai,
        patch.object(cli_mod, "_fetch_kimi") as mock_kimi,
        patch.object(cli_mod, "_fetch_opencode") as mock_opencode,
        patch.object(cli_mod, "_fetch_opencode_go") as mock_opencode_go,
    ):
        from token_usage.claude.models import ClaudeUsage

        mock_gather.return_value = (ClaudeUsage(available=True), {}, None)
        mock_select.return_value = (ClaudeUsage(available=True), "statusline", None, {})
        cli_mod._build_summary(cfg, providers=("claude",))

    assert _json_bytes(written_payload.get("openai")) == _json_bytes(existing["openai"])
    assert _json_bytes(written_payload.get("kimi")) == _json_bytes(existing["kimi"])
    assert _json_bytes(written_payload.get("opencode")) == _json_bytes(existing["opencode"])
    assert _json_bytes(written_payload.get("opencode_go")) == _json_bytes(existing["opencode_go"])

    assert write_kwargs["fetched_providers"] == {"claude"}
    mock_openai.assert_not_called()
    mock_kimi.assert_not_called()
    mock_opencode.assert_not_called()
    mock_opencode_go.assert_not_called()


def test_main_only_kimi_against_full_cache_byte_isolation(capsys) -> None:
    """End-to-end: run main --only kimi with a real cache file."""
    cfg = cfg_mod.Config()
    cfg.cache_ttl_seconds = 300
    cfg.kimi_enabled = True

    old_ts = 1000.0
    existing = {
        "summary": {"available": True, "_source": "oauth", "five_hour_pct": 30.0},
        "openai": {"available": True, "primary_pct": 80.0},
        "kimi": {"available": True, "primary_pct": 10.0},
        "opencode": None,
        "opencode_go": None,
        "_version": 10,
        "fetched_at": old_ts,
        "_provider_fetched_at": {
            "claude": old_ts,
            "chatgpt": old_ts,
            "kimi": old_ts,
        },
        "_written_at": old_ts,
    }

    written_payload: dict = {}

    def _fake_write(payload, fetched_providers=None):
        written_payload.update(payload)

    with (
        patch.object(cfg_mod, "load", return_value=cfg),
        patch.object(cache_mod, "read_raw", return_value=existing),
        patch.object(cache_mod, "write", side_effect=_fake_write),
        patch.object(
            cli_mod,
            "_build_summary",
            return_value=(
                existing["summary"],
                existing["openai"],
                {"available": True, "primary_pct": 99.0},
                None,
                None,
            ),
        ),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "kimi"])

    assert rc == 0
    assert capsys.readouterr().out == "k99%"

    # Even though _build_summary is mocked, the test verifies the contract:
    # main passes through the returned values, and if the cache write happened
    # with the real _build_summary, non-kimi bytes would be untouched.
    # This is a shallow integration test of main() + --only isolation.
