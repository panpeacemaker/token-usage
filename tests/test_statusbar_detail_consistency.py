from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from token_usage.formatters import statusbar, detail


def _extract_statusbar_pct(segment: str) -> float:
    """Extract the numeric percentage from a statusbar segment like 'c42%@14:00'."""
    m = re.search(r"[ckeog](\d+(?:\.\d+)?)%", segment)
    assert m, f"no pct found in statusbar segment: {segment!r}"
    return float(m.group(1))


def _extract_bar_pct(detail_text: str) -> float:
    """Find the line with '← bar' and extract its percentage."""
    for line in detail_text.split("\n"):
        if "← bar" in line:
            m = re.search(r"(\d+(?:\.\d+)?)%", line)
            assert m, f"no pct found in bar line: {line!r}"
            return float(m.group(1))
    raise AssertionError(f"no ← bar marker found in detail text")


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

RESET_5H = datetime(2099, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
RESET_7D = datetime(2099, 4, 13, 20, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "five_hour_pct, seven_day_pct",
    [
        (60.0, 50.0),   # 5h drives
        (30.0, 80.0),   # 7d drives
        (50.0, 50.0),   # tie → 5h wins
        (10.0, 0.0),    # only 5h non-zero
        (0.0, 10.0),    # only 7d non-zero
    ],
)
def test_claude_statusbar_detail_consistency(five_hour_pct, seven_day_pct) -> None:
    summary = {
        "available": True,
        "five_hour_pct": five_hour_pct,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": seven_day_pct,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    sb = statusbar.format_compact(summary)
    det = detail.format_detail(summary)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det)


# ---------------------------------------------------------------------------
# ChatGPT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "primary_pct, weekly_pct",
    [
        (50.0, 20.0),   # primary drives
        (10.0, 90.0),   # weekly drives
        (50.0, 50.0),   # tie → primary wins
        (5.0, 0.0),     # only primary non-zero
        (0.0, 5.0),     # only weekly non-zero
    ],
)
def test_chatgpt_statusbar_detail_consistency(primary_pct, weekly_pct) -> None:
    openai = {
        "available": True,
        "primary_pct": primary_pct,
        "primary_reset_at": 4081503240,
        "weekly_pct": weekly_pct,
        "weekly_reset_at": 4082100040,
    }
    sb = statusbar.format_compact({}, openai)
    det = detail.format_detail(None, openai)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det)


# ---------------------------------------------------------------------------
# Kimi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "primary_pct, weekly_pct",
    [
        (25.0, 10.0),   # 5h drives
        (5.0, 80.0),    # weekly drives
        (30.0, 30.0),   # tie → 5h wins
        (10.0, 0.0),    # only 5h non-zero
        (0.0, 10.0),    # only weekly non-zero
    ],
)
def test_kimi_statusbar_detail_consistency(primary_pct, weekly_pct) -> None:
    kimi = {
        "available": True,
        "primary_pct": primary_pct,
        "primary_reset_at": 4081503240,
        "weekly_pct": weekly_pct,
        "weekly_reset_at": 4082100040,
    }
    sb = statusbar.format_compact({}, None, kimi)
    det = detail.format_detail(None, None, kimi)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det)


# ---------------------------------------------------------------------------
# OpenCode
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "primary_pct, weekly_pct",
    [
        (50.0, 10.0),   # 5h drives
        (5.0, 40.0),    # weekly drives
        (20.0, 20.0),   # tie → 5h wins
        (10.0, 0.0),    # only 5h non-zero
        (0.0, 10.0),    # only weekly non-zero
    ],
)
def test_opencode_statusbar_detail_consistency(primary_pct, weekly_pct) -> None:
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "primary_pct": primary_pct,
        "primary_reset_at": 4081503240,
        "weekly_pct": weekly_pct,
        "weekly_reset_at": 4082100040,
    }
    sb = statusbar.format_compact({}, None, None, opencode)
    det = detail.format_detail(None, None, None, opencode)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det)


# ---------------------------------------------------------------------------
# OpenCode-Go
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "primary_pct, weekly_pct",
    [
        (70.0, 10.0),   # 5h drives
        (5.0, 60.0),    # weekly drives
        (15.0, 15.0),   # tie → 5h wins
        (10.0, 0.0),    # only 5h non-zero
        (0.0, 10.0),    # only weekly non-zero
    ],
)
def test_opencode_go_statusbar_detail_consistency(primary_pct, weekly_pct) -> None:
    opencode_go = {
        "available": True,
        "provider_id": "opencode-go",
        "primary_pct": primary_pct,
        "primary_reset_at": 4081503240,
        "weekly_pct": weekly_pct,
        "weekly_reset_at": 4082100040,
    }
    sb = statusbar.format_compact({}, None, None, None, opencode_go)
    det = detail.format_detail(None, None, None, None, opencode_go)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det)


# ---------------------------------------------------------------------------
# Multi-provider combined: each section's bar marker matches its segment
# ---------------------------------------------------------------------------

def test_combined_three_provider_consistency() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 80.0,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    openai = {
        "available": True,
        "primary_pct": 90.0,
        "primary_reset_at": 4081503240,
        "weekly_pct": 10.0,
        "weekly_reset_at": 4082100040,
    }
    kimi = {
        "available": True,
        "primary_pct": 5.0,
        "primary_reset_at": 4081503240,
        "weekly_pct": 50.0,
        "weekly_reset_at": 4082100040,
    }

    sb = statusbar.format_compact(summary, openai, kimi)
    det = detail.format_detail(summary, openai, kimi)

    # Statusbar has 3 segments
    segments = sb.split(" ")
    assert len(segments) == 3

    # Each segment pct should match the bar-marked window in its detail section
    # We can verify by checking that for each provider, the max pct in its data
    # equals both the statusbar segment pct and the detail bar pct.
    assert _extract_statusbar_pct(segments[0]) == 80.0  # claude: 7d=80 > 5h=30
    assert _extract_statusbar_pct(segments[1]) == 90.0  # chatgpt: primary=90 > weekly=10
    assert _extract_statusbar_pct(segments[2]) == 50.0  # kimi: weekly=50 > 5h=5

    # Extract bar pcts from each section
    sections = det.split("\n\n")
    bar_pcts = [_extract_bar_pct(section) for section in sections]
    assert bar_pcts == [80.0, 90.0, 50.0]


# ---------------------------------------------------------------------------
# Override: statusbar and detail agree when bar_window is pinned per provider
# ---------------------------------------------------------------------------

def test_override_per_provider_consistency() -> None:
    """Each provider pinned to the window that's NOT the max — both renderers agree."""
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 80.0,  # 7d is max, but claude is pinned to 5h
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    openai = {
        "available": True,
        "primary_pct": 90.0,
        "primary_reset_at": 4081503240,  # primary is max, but openai is pinned to weekly
        "weekly_pct": 10.0,
        "weekly_reset_at": 4082100040,
    }
    kimi = {
        "available": True,
        "primary_pct": 5.0,
        "primary_reset_at": 4081503240,  # 5h is min, but kimi is pinned to 5h
        "weekly_pct": 50.0,
        "weekly_reset_at": 4082100040,
    }
    bar_windows = {"claude": "5h", "openai": "weekly", "kimi": "5h"}

    sb = statusbar.format_compact(summary, openai, kimi, bar_windows=bar_windows)
    det = detail.format_detail(summary, openai, kimi, bar_windows=bar_windows)

    segments = sb.split(" ")
    assert _extract_statusbar_pct(segments[0]) == 30.0  # claude pinned 5h
    assert _extract_statusbar_pct(segments[1]) == 10.0  # openai pinned weekly
    assert _extract_statusbar_pct(segments[2]) == 5.0   # kimi pinned 5h

    sections = det.split("\n\n")
    bar_pcts = [_extract_bar_pct(section) for section in sections]
    assert bar_pcts == [30.0, 10.0, 5.0]
    assert _extract_statusbar_pct(segments[0]) == bar_pcts[0]
    assert _extract_statusbar_pct(segments[1]) == bar_pcts[1]
    assert _extract_statusbar_pct(segments[2]) == bar_pcts[2]
