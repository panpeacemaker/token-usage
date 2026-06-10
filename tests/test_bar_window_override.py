from __future__ import annotations

from datetime import datetime, timezone

from token_usage.formatters import statusbar, detail


RESET_5H = datetime(2099, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
RESET_7D = datetime(2099, 4, 13, 20, 0, 0, tzinfo=timezone.utc)
RESET_PRIMARY_EPOCH = 4081503240
RESET_WEEKLY_EPOCH = 4082100040
RESET_PRIMARY_HHMM = datetime.fromtimestamp(RESET_PRIMARY_EPOCH, tz=timezone.utc).astimezone().strftime("%H:%M")
RESET_WEEKLY_HHMM = datetime.fromtimestamp(RESET_WEEKLY_EPOCH, tz=timezone.utc).astimezone().strftime("%H:%M")


# ---------------------------------------------------------------------------
# Statusbar: override picks the named window even when it's not the max
# ---------------------------------------------------------------------------

def test_statusbar_claude_override_5h_even_when_7d_higher() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 92.0,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    result = statusbar.format_compact(summary, bar_windows={"claude": "5h"})
    assert result == f"c30%@{RESET_5H.astimezone().strftime('%H:%M')}"


def test_statusbar_claude_override_7d_even_when_5h_higher() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 80.0,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 20.0,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    result = statusbar.format_compact(summary, bar_windows={"claude": "7d"})
    assert result == f"c20%@{RESET_7D.astimezone().strftime('%H:%M')}"


def test_statusbar_openai_override_primary_even_when_weekly_higher() -> None:
    openai = {
        "available": True,
        "primary_pct": 20.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 95.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    result = statusbar.format_compact({}, openai, bar_windows={"openai": "primary"})
    assert result == f"o20%@{RESET_PRIMARY_HHMM}"


def test_statusbar_openai_override_weekly_even_when_primary_higher() -> None:
    openai = {
        "available": True,
        "primary_pct": 90.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 30.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    result = statusbar.format_compact({}, openai, bar_windows={"openai": "weekly"})
    assert result == f"o30%@{RESET_WEEKLY_HHMM}"


def test_statusbar_kimi_override_5h_even_when_weekly_higher() -> None:
    kimi = {
        "available": True,
        "primary_pct": 12.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 80.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    result = statusbar.format_compact({}, None, kimi, bar_windows={"kimi": "5h"})
    assert result == f"k12%@{RESET_PRIMARY_HHMM}"


def test_statusbar_kimi_override_weekly_even_when_5h_higher() -> None:
    kimi = {
        "available": True,
        "primary_pct": 70.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 15.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    result = statusbar.format_compact({}, None, kimi, bar_windows={"kimi": "weekly"})
    assert result == f"k15%@{RESET_WEEKLY_HHMM}"


def test_statusbar_opencode_override_5h_even_when_weekly_higher() -> None:
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "primary_pct": 8.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 88.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    result = statusbar.format_compact({}, None, None, opencode, bar_windows={"opencode": "5h"})
    assert result == f"e8%~{RESET_PRIMARY_HHMM}"


def test_statusbar_opencode_go_override_weekly_even_when_5h_higher() -> None:
    opencode_go = {
        "available": True,
        "provider_id": "opencode-go",
        "primary_pct": 50.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 20.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    result = statusbar.format_compact({}, None, None, None, opencode_go, bar_windows={"opencode-go": "weekly"})
    assert result == f"g20%~{RESET_WEEKLY_HHMM}"


# ---------------------------------------------------------------------------
# Override falls back to max-rule when pinned window is missing/expired
# ---------------------------------------------------------------------------

def test_statusbar_claude_override_expired_5h_falls_back_to_7d() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 0.0,
        "five_hour_resets_at": None,
        "_five_hour_expired": True,
        "seven_day_pct": 45.0,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    result = statusbar.format_compact(summary, bar_windows={"claude": "5h"})
    assert result == f"c45%@{RESET_7D.astimezone().strftime('%H:%M')}"


def test_statusbar_claude_override_expired_7d_falls_back_to_5h() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 33.0,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 0.0,
        "seven_day_resets_at": None,
        "_seven_day_expired": True,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    result = statusbar.format_compact(summary, bar_windows={"claude": "7d"})
    assert result == f"c33%@{RESET_5H.astimezone().strftime('%H:%M')}"


def test_statusbar_openai_override_missing_primary_falls_back_to_weekly() -> None:
    openai = {
        "available": True,
        "primary_pct": None,
        "primary_reset_at": None,
        "weekly_pct": 42.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    result = statusbar.format_compact({}, openai, bar_windows={"openai": "primary"})
    assert result == f"o42%@{RESET_WEEKLY_HHMM}"


def test_statusbar_kimi_override_missing_weekly_falls_back_to_5h() -> None:
    kimi = {
        "available": True,
        "primary_pct": 7.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": None,
        "weekly_reset_at": None,
    }
    result = statusbar.format_compact({}, None, kimi, bar_windows={"kimi": "weekly"})
    assert result == f"k7%@{RESET_PRIMARY_HHMM}"


def test_statusbar_both_claude_windows_expired_with_override_still_renders_zero() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 0.0,
        "five_hour_resets_at": None,
        "_five_hour_expired": True,
        "seven_day_pct": 0.0,
        "seven_day_resets_at": None,
        "_seven_day_expired": True,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    result = statusbar.format_compact(summary, bar_windows={"claude": "5h"})
    assert result == "c0%"


def test_statusbar_unknown_label_falls_back_to_max() -> None:
    openai = {
        "available": True,
        "primary_pct": 10.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 90.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    result = statusbar.format_compact({}, openai, bar_windows={"openai": "nonsense"})
    assert result == f"o90%@{RESET_WEEKLY_HHMM}"


# ---------------------------------------------------------------------------
# Detail: ← bar marker follows the override
# ---------------------------------------------------------------------------

def test_detail_openai_bar_marker_on_primary_when_override_primary() -> None:
    openai = {
        "available": True,
        "primary_pct": 10.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 90.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    out = detail.format_detail(None, openai, bar_windows={"openai": "primary"})
    lines = out.split("\n")
    primary_line = [l for l in lines if "primary:" in l][0]
    weekly_line = [l for l in lines if "weekly:" in l][0]
    assert "← bar" in primary_line
    assert "← bar" not in weekly_line


def test_detail_openai_bar_marker_on_weekly_when_override_weekly() -> None:
    openai = {
        "available": True,
        "primary_pct": 95.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 10.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    out = detail.format_detail(None, openai, bar_windows={"openai": "weekly"})
    lines = out.split("\n")
    primary_line = [l for l in lines if "primary:" in l][0]
    weekly_line = [l for l in lines if "weekly:" in l][0]
    assert "← bar" not in primary_line
    assert "← bar" in weekly_line


def test_detail_kimi_bar_marker_on_5h_when_override_5h() -> None:
    kimi = {
        "available": True,
        "primary_pct": 5.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 80.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    out = detail.format_detail(None, None, kimi, bar_windows={"kimi": "5h"})
    lines = out.split("\n")
    five_line = [l for l in lines if "5-hour:" in l][0]
    weekly_line = [l for l in lines if "weekly:" in l][0]
    assert "← bar" in five_line
    assert "← bar" not in weekly_line


def test_detail_claude_bar_marker_on_5h_when_override_5h() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 20.0,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 80.0,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    out = detail.format_detail(summary, bar_windows={"claude": "5h"})
    lines = out.split("\n")
    five_line = [l for l in lines if "5-hour:" in l][0]
    seven_line = [l for l in lines if "7-day:" in l][0]
    assert "← bar" in five_line
    assert "← bar" not in seven_line


def test_detail_claude_override_5h_expired_falls_back_marker_to_7d() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 0.0,
        "five_hour_resets_at": None,
        "_five_hour_expired": True,
        "seven_day_pct": 45.0,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    out = detail.format_detail(summary, bar_windows={"claude": "5h"})
    lines = out.split("\n")
    seven_line = [l for l in lines if "7-day:" in l][0]
    assert "← bar" in seven_line


# ---------------------------------------------------------------------------
# Statusbar/Detail consistency with override
# ---------------------------------------------------------------------------

def _extract_statusbar_pct(segment: str) -> float:
    import re
    m = re.search(r"[ckeog](\d+(?:\.\d+)?)%", segment)
    assert m, f"no pct found in {segment!r}"
    return float(m.group(1))


def _extract_bar_pct(detail_text: str) -> float:
    import re
    for line in detail_text.split("\n"):
        if "← bar" in line:
            m = re.search(r"(\d+(?:\.\d+)?)%", line)
            assert m, f"no pct in bar line: {line!r}"
            return float(m.group(1))
    raise AssertionError("no ← bar marker in detail text")


def test_statusbar_detail_consistency_openai_with_override() -> None:
    openai = {
        "available": True,
        "primary_pct": 10.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 90.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    bw = {"openai": "primary"}
    sb = statusbar.format_compact({}, openai, bar_windows=bw)
    det = detail.format_detail(None, openai, bar_windows=bw)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det) == 10.0


def test_statusbar_detail_consistency_kimi_with_override() -> None:
    kimi = {
        "available": True,
        "primary_pct": 7.0,
        "primary_reset_at": RESET_PRIMARY_EPOCH,
        "weekly_pct": 88.0,
        "weekly_reset_at": RESET_WEEKLY_EPOCH,
    }
    bw = {"kimi": "weekly"}
    sb = statusbar.format_compact({}, None, kimi, bar_windows=bw)
    det = detail.format_detail(None, None, kimi, bar_windows=bw)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det) == 88.0


def test_statusbar_detail_consistency_claude_with_override() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 25.0,
        "five_hour_resets_at": RESET_5H,
        "seven_day_pct": 75.0,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    bw = {"claude": "7d"}
    sb = statusbar.format_compact(summary, bar_windows=bw)
    det = detail.format_detail(summary, bar_windows=bw)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det) == 75.0


def test_statusbar_detail_consistency_override_expired_falls_back() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 0.0,
        "five_hour_resets_at": None,
        "_five_hour_expired": True,
        "seven_day_pct": 60.0,
        "seven_day_resets_at": RESET_7D,
        "subscription_type": "claude-code",
        "rate_limit_tier": "claude-code",
    }
    bw = {"claude": "5h"}  # 5h is expired → should fall back to 7d
    sb = statusbar.format_compact(summary, bar_windows=bw)
    det = detail.format_detail(summary, bar_windows=bw)
    assert _extract_statusbar_pct(sb) == _extract_bar_pct(det) == 60.0
