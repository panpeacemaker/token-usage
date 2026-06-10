from __future__ import annotations

from unittest.mock import patch

from token_usage import config as cfg_mod


def _load(text: str, tmp_path) -> cfg_mod.Config:
    p = tmp_path / "config.toml"
    p.write_text(text)
    with patch.object(cfg_mod, "CONFIG_FILE", p):
        return cfg_mod.load()


def test_defaults_all_max(tmp_path) -> None:
    cfg = _load("", tmp_path)
    assert cfg.claude_bar_window == "max"
    assert cfg.openai_bar_window == "max"
    assert cfg.kimi_bar_window == "max"
    assert cfg.opencode_bar_window == "max"
    assert cfg.opencode_go_bar_window == "max"


def test_dataclass_defaults_all_max() -> None:
    cfg = cfg_mod.Config()
    assert cfg.claude_bar_window == "max"
    assert cfg.openai_bar_window == "max"
    assert cfg.kimi_bar_window == "max"
    assert cfg.opencode_bar_window == "max"
    assert cfg.opencode_go_bar_window == "max"


def test_claude_bar_window_5h(tmp_path) -> None:
    cfg = _load('[claude]\nbar_window = "5h"\n', tmp_path)
    assert cfg.claude_bar_window == "5h"


def test_claude_bar_window_7d(tmp_path) -> None:
    cfg = _load('[claude]\nbar_window = "7d"\n', tmp_path)
    assert cfg.claude_bar_window == "7d"


def test_openai_bar_window_primary(tmp_path) -> None:
    cfg = _load('[openai]\nbar_window = "primary"\n', tmp_path)
    assert cfg.openai_bar_window == "primary"


def test_openai_bar_window_weekly(tmp_path) -> None:
    cfg = _load('[openai]\nbar_window = "weekly"\n', tmp_path)
    assert cfg.openai_bar_window == "weekly"


def test_kimi_bar_window_5h(tmp_path) -> None:
    cfg = _load('[kimi]\nbar_window = "5h"\n', tmp_path)
    assert cfg.kimi_bar_window == "5h"


def test_kimi_bar_window_weekly(tmp_path) -> None:
    cfg = _load('[kimi]\nbar_window = "weekly"\n', tmp_path)
    assert cfg.kimi_bar_window == "weekly"


def test_opencode_bar_window_5h(tmp_path) -> None:
    cfg = _load('[opencode]\nbar_window = "5h"\n', tmp_path)
    assert cfg.opencode_bar_window == "5h"


def test_opencode_bar_window_weekly(tmp_path) -> None:
    cfg = _load('[opencode]\nbar_window = "weekly"\n', tmp_path)
    assert cfg.opencode_bar_window == "weekly"


def test_opencode_go_bar_window_5h(tmp_path) -> None:
    cfg = _load('[opencode-go]\nbar_window = "5h"\n', tmp_path)
    assert cfg.opencode_go_bar_window == "5h"


def test_opencode_go_bar_window_weekly(tmp_path) -> None:
    cfg = _load('[opencode-go]\nbar_window = "weekly"\n', tmp_path)
    assert cfg.opencode_go_bar_window == "weekly"


def test_opencode_bar_window_monthly(tmp_path) -> None:
    cfg = _load('[opencode]\nbar_window = "monthly"\n', tmp_path)
    assert cfg.opencode_bar_window == "monthly"


def test_opencode_go_bar_window_monthly(tmp_path) -> None:
    cfg = _load('[opencode-go]\nbar_window = "monthly"\n', tmp_path)
    assert cfg.opencode_go_bar_window == "monthly"


def test_claude_invalid_value_falls_back_to_max(tmp_path) -> None:
    cfg = _load('[claude]\nbar_window = "bogus"\n', tmp_path)
    assert cfg.claude_bar_window == "max"


def test_openai_invalid_value_falls_back_to_max(tmp_path) -> None:
    cfg = _load('[openai]\nbar_window = "5h"\n', tmp_path)
    assert cfg.openai_bar_window == "max"


def test_kimi_invalid_value_falls_back_to_max(tmp_path) -> None:
    cfg = _load('[kimi]\nbar_window = "primary"\n', tmp_path)
    assert cfg.kimi_bar_window == "max"


def test_opencode_invalid_value_falls_back_to_max(tmp_path) -> None:
    cfg = _load('[opencode]\nbar_window = "daily"\n', tmp_path)
    assert cfg.opencode_bar_window == "max"


def test_opencode_go_invalid_value_falls_back_to_max(tmp_path) -> None:
    cfg = _load('[opencode-go]\nbar_window = "yearly"\n', tmp_path)
    assert cfg.opencode_go_bar_window == "max"


def test_bar_window_value_normalised_lowercase(tmp_path) -> None:
    cfg = _load('[openai]\nbar_window = "PRIMARY"\n', tmp_path)
    assert cfg.openai_bar_window == "primary"


def test_bar_window_non_string_falls_back_to_max(tmp_path) -> None:
    cfg = _load('[openai]\nbar_window = 42\n', tmp_path)
    assert cfg.openai_bar_window == "max"


def test_all_providers_parsed_in_one_config(tmp_path) -> None:
    cfg = _load(
        '[claude]\nbar_window = "7d"\n'
        '[openai]\nbar_window = "primary"\n'
        '[kimi]\nbar_window = "weekly"\n'
        '[opencode]\nbar_window = "5h"\n'
        '[opencode-go]\nbar_window = "weekly"\n',
        tmp_path,
    )
    assert cfg.claude_bar_window == "7d"
    assert cfg.openai_bar_window == "primary"
    assert cfg.kimi_bar_window == "weekly"
    assert cfg.opencode_bar_window == "5h"
    assert cfg.opencode_go_bar_window == "weekly"


def test_explicit_max_is_preserved(tmp_path) -> None:
    cfg = _load('[claude]\nbar_window = "max"\n[openai]\nbar_window = "max"\n', tmp_path)
    assert cfg.claude_bar_window == "max"
    assert cfg.openai_bar_window == "max"
