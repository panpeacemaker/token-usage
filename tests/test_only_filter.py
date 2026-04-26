from __future__ import annotations

from unittest.mock import patch

from token_usage import cache as cache_mod
from token_usage import cli as cli_mod
from token_usage import config as cfg_mod


def _build_cfg(**overrides):
    cfg = cfg_mod.Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_normalize_providers_csv_string() -> None:
    assert cfg_mod._normalize_providers("claude,kimi") == ("claude", "kimi")


def test_normalize_providers_aliases() -> None:
    assert cfg_mod._normalize_providers("c, o, k") == ("claude", "chatgpt", "kimi")
    assert cfg_mod._normalize_providers("openai") == ("chatgpt",)


def test_normalize_providers_empty_falls_back_to_all() -> None:
    assert cfg_mod._normalize_providers("") == cfg_mod.ALL_PROVIDERS
    assert cfg_mod._normalize_providers([]) == cfg_mod.ALL_PROVIDERS


def test_normalize_providers_dedupes_and_filters_unknown() -> None:
    assert cfg_mod._normalize_providers(["claude", "claude", "bogus", "kimi"]) == ("claude", "kimi")


def test_build_summary_skips_chatgpt_and_kimi_when_only_claude(monkeypatch) -> None:
    cfg = _build_cfg(cache_ttl_seconds=0)
    with (
        patch.object(cache_mod, "read", return_value=None),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(cli_mod, "_gather_sources") as mock_gather,
        patch.object(cli_mod, "_select_claude_source") as mock_select,
        patch.object(cli_mod, "_assemble_summary", return_value={"available": True, "_source": "test"}),
        patch.object(cli_mod, "_fetch_openai") as mock_openai,
        patch.object(cli_mod, "_fetch_kimi") as mock_kimi,
    ):
        from token_usage.claude.models import ClaudeUsage

        mock_gather.return_value = (ClaudeUsage(available=True), {}, None)
        mock_select.return_value = (ClaudeUsage(available=True), "oauth", None)
        summary, openai, kimi = cli_mod._build_summary(cfg, providers=("claude",))
    assert summary["_source"] == "test"
    assert openai is None
    assert kimi is None
    mock_openai.assert_not_called()
    mock_kimi.assert_not_called()


def test_build_summary_skips_claude_fetch_when_only_kimi() -> None:
    cfg = _build_cfg(cache_ttl_seconds=0)
    with (
        patch.object(cache_mod, "read", return_value=None),
        patch.object(cache_mod, "read_raw", return_value=None),
        patch.object(cache_mod, "write"),
        patch.object(cli_mod, "_gather_sources") as mock_gather,
        patch.object(cli_mod, "_fetch_openai") as mock_openai,
        patch.object(cli_mod, "_fetch_kimi", return_value={"available": True, "primary_pct": 1.0}),
    ):
        summary, openai, kimi = cli_mod._build_summary(cfg, providers=("kimi",))
    assert summary["_source"] == "skipped"
    assert kimi == {"available": True, "primary_pct": 1.0}
    assert openai is None
    mock_gather.assert_not_called()
    mock_openai.assert_not_called()


def test_partial_only_call_preserves_other_providers_in_cache() -> None:
    cfg = _build_cfg(cache_ttl_seconds=0)
    existing = {
        "summary": {"available": True, "_source": "oauth", "five_hour_pct": 30},
        "openai": {"available": True, "primary_pct": 80.0},
        "kimi": {"available": True, "primary_pct": 10.0},
        "_version": 7,
        "fetched_at": 0,
    }
    written: dict = {}

    def _fake_write(payload):
        written.update(payload)

    with (
        patch.object(cache_mod, "read", return_value=None),
        patch.object(cache_mod, "read_raw", return_value=existing),
        patch.object(cache_mod, "write", side_effect=_fake_write),
        patch.object(cli_mod, "_fetch_kimi", return_value={"available": True, "primary_pct": 99.0}),
        patch.object(cli_mod, "_gather_sources") as mock_gather,
        patch.object(cli_mod, "_fetch_openai") as mock_openai,
    ):
        summary, openai, kimi = cli_mod._build_summary(cfg, providers=("kimi",))
    assert summary == existing["summary"]
    assert openai == existing["openai"]
    assert kimi == {"available": True, "primary_pct": 99.0}
    assert written["summary"] == existing["summary"]
    assert written["openai"] == existing["openai"]
    assert written["kimi"] == {"available": True, "primary_pct": 99.0}
    mock_gather.assert_not_called()
    mock_openai.assert_not_called()


def test_cache_with_null_chatgpt_triggers_refetch_when_chatgpt_selected() -> None:
    cfg = _build_cfg(cache_ttl_seconds=300)
    cfg.openai_enabled = True
    cfg.kimi_enabled = True
    poisoned = {
        "summary": {"available": True, "_source": "oauth"},
        "openai": None,
        "kimi": None,
        "_version": 7,
        "fetched_at": 0,
    }
    with (
        patch.object(cache_mod, "read", return_value=poisoned),
        patch.object(cache_mod, "read_raw", return_value=poisoned),
        patch.object(cache_mod, "write"),
        patch.object(cli_mod, "_fetch_openai", return_value={"available": True, "primary_pct": 5.0}) as mock_openai,
        patch.object(cli_mod, "_fetch_kimi") as mock_kimi,
    ):
        summary, openai, kimi = cli_mod._build_summary(cfg, providers=("chatgpt",))
    assert summary == poisoned["summary"]
    assert openai == {"available": True, "primary_pct": 5.0}
    assert kimi is None
    mock_openai.assert_called_once()
    mock_kimi.assert_not_called()


def test_main_only_kimi_renders_bare(capsys) -> None:
    cfg = cfg_mod.Config()
    with (
        patch.object(cfg_mod, "load", return_value=cfg),
        patch.object(
            cli_mod,
            "_build_summary",
            return_value=({"available": False, "_source": "skipped"}, None, {"available": True, "primary_pct": 7.0}),
        ),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "kimi"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("K ")
    assert not out.startswith("| ")
    assert "C " not in out
    assert "O " not in out


def test_main_only_csv_renders_combined_framing(capsys) -> None:
    cfg = cfg_mod.Config()
    with (
        patch.object(cfg_mod, "load", return_value=cfg),
        patch.object(
            cli_mod,
            "_build_summary",
            return_value=(
                {"available": True, "five_hour_pct": 10.0, "seven_day_pct": 0.0, "five_hour_resets_at": None},
                None,
                {"available": True, "primary_pct": 5.0, "weekly_pct": 0.0},
            ),
        ),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "claude,kimi"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("| ")
    assert "C 10%" in out
    assert "K 5%" in out
    assert "O " not in out


def test_main_only_unknown_falls_back_to_all(capsys) -> None:
    cfg = cfg_mod.Config()
    with (
        patch.object(cfg_mod, "load", return_value=cfg),
        patch.object(
            cli_mod,
            "_build_summary",
            return_value=(
                {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 0.0, "five_hour_resets_at": None},
                {"available": True, "primary_pct": 0.0, "weekly_pct": 0.0},
                {"available": True, "primary_pct": 0.0, "weekly_pct": 0.0},
            ),
        ),
    ):
        rc = cli_mod.main(["--statusbar", "--only", "bogus"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "C 1%" in out
    assert "O 0%" in out
    assert "K 0%" in out


def test_config_statusbar_providers_default() -> None:
    cfg = cfg_mod.Config()
    assert cfg.statusbar_providers == cfg_mod.ALL_PROVIDERS
