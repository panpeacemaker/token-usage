from __future__ import annotations

import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from token_usage import cli as cli_mod
from token_usage import cache as cache_mod
from token_usage import config as config_mod
from token_usage.claude import local_summary as local_summary_mod
from token_usage.claude import oauth_usage as oauth_mod
from token_usage.claude import statusline as statusline_mod
from token_usage.claude.models import ClaudeUsage


def _stub_summary():
    now = datetime.now(timezone.utc)
    return ClaudeUsage(
        available=True,
        five_hour_pct=42.0,
        five_hour_resets_at=now + timedelta(hours=2),
        seven_day_pct=15.0,
        seven_day_resets_at=now + timedelta(days=3),
        subscription_type="claude-code",
        rate_limit_tier="claude-code",
    )


def _enter_patches(stack: ExitStack) -> None:
    stack.enter_context(patch.object(cache_mod, "read_raw", return_value=None))
    stack.enter_context(patch.object(cache_mod, "write"))
    stack.enter_context(patch.object(statusline_mod, "read_statusline_usage", return_value=_stub_summary()))
    stack.enter_context(patch.object(cli_mod, "_statusline_mtime", return_value=time.time()))
    stack.enter_context(
        patch.object(oauth_mod, "fetch_usage", return_value=ClaudeUsage(available=False, error="http 429"))
    )
    stack.enter_context(
        patch.object(
            local_summary_mod,
            "compute_local",
            return_value=(
                ClaudeUsage(available=False, error="none"),
                {"total_entries": 0},
            ),
        )
    )


def test_statusbar_is_default(capsys):
    with ExitStack() as stack:
        _enter_patches(stack)
        rc = cli_mod.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "c42%" in out


def test_detail_flag(capsys):
    with ExitStack() as stack:
        _enter_patches(stack)
        rc = cli_mod.main(["--detail"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Claude" in out


def test_json_flag(capsys):
    with ExitStack() as stack:
        _enter_patches(stack)
        rc = cli_mod.main(["--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"claude"' in out


def test_version_flag(capsys):
    with pytest.raises(SystemExit, match="0"):
        cli_mod.main(["--version"])
    out = capsys.readouterr().out
    assert "token-usage" in out


def test_no_cache_bypasses(capsys):
    with ExitStack() as stack:
        _enter_patches(stack)
        rc = cli_mod.main(["--no-cache"])
    assert rc == 0


def test_error_handling(capsys):
    with (
        patch.object(config_mod, "load", return_value=config_mod.Config()),
        patch.object(cli_mod, "_build_summary", side_effect=RuntimeError("boom")),
    ):
        rc = cli_mod.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "boom" in err
    assert "Traceback" in err
