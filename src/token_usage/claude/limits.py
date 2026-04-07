"""Conservative Claude plan ceilings calibrated to observed usage.

Anthropic does not publish exact token limits, so these defaults use roughly
2x the user's observed p99 historical usage as a safe ceiling. Override any
plan in ~/.config/token-usage/config.toml when local usage differs. Weekly
message caps are more reliable than token caps, so keep messages_weekly as the
primary published constraint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    name: str
    tokens_5h: int
    tokens_weekly: int
    messages_weekly: int


DEFAULT_LIMITS: dict[str, PlanLimits] = {
    "pro": PlanLimits("pro", tokens_5h=20_000_000, tokens_weekly=400_000_000, messages_weekly=250),
    "max5": PlanLimits("max5", tokens_5h=100_000_000, tokens_weekly=2_000_000_000, messages_weekly=1_000),
    "max20": PlanLimits("max20", tokens_5h=400_000_000, tokens_weekly=8_000_000_000, messages_weekly=2_000),
}


def get_limits(plan: str, overrides: dict | None = None) -> PlanLimits:
    base = DEFAULT_LIMITS.get(plan, DEFAULT_LIMITS["pro"])
    if not overrides:
        return base
    plan_over = overrides.get(plan) or {}
    return PlanLimits(
        name=base.name,
        tokens_5h=int(plan_over.get("tokens_5h", base.tokens_5h)),
        tokens_weekly=int(plan_over.get("tokens_weekly", base.tokens_weekly)),
        messages_weekly=int(plan_over.get("messages_weekly", base.messages_weekly)),
    )
