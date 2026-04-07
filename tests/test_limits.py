from __future__ import annotations

from token_usage.claude.limits import DEFAULT_LIMITS, get_limits


def test_defaults() -> None:
    l = get_limits("pro")
    assert l.name == "pro"
    assert l.tokens_5h == 19_000


def test_override() -> None:
    l = get_limits("pro", {"pro": {"tokens_5h": 50_000}})
    assert l.tokens_5h == 50_000
    assert l.tokens_weekly == DEFAULT_LIMITS["pro"].tokens_weekly
