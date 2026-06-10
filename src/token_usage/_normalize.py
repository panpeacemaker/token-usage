from __future__ import annotations

import time

OPENAI_WINDOW_FIELDS: tuple[tuple[str, str], ...] = (
    ("primary_pct", "primary_reset_at"),
    ("weekly_pct", "weekly_reset_at"),
    ("review_pct", "review_reset_at"),
)

KIMI_WINDOW_FIELDS: tuple[tuple[str, str], ...] = (
    ("primary_pct", "primary_reset_at"),
    ("weekly_pct", "weekly_reset_at"),
)

OPENCODE_WINDOW_FIELDS: tuple[tuple[str, str], ...] = (
    ("primary_pct", "primary_reset_at"),
    ("weekly_pct", "weekly_reset_at"),
    ("monthly_pct", "monthly_reset_at"),
)


def normalize_windows(
    payload: dict | None,
    fields: tuple[tuple[str, str], ...],
    now: int | None = None,
) -> dict | None:
    if payload is None:
        return None
    payload = dict(payload)
    if not payload.get("available"):
        return payload
    epoch = int(now if now is not None else time.time())
    for pct_field, reset_field in fields:
        reset = payload.get(reset_field)
        if reset is None:
            continue
        try:
            reset_epoch = int(float(reset))
        except (TypeError, ValueError):
            continue
        if reset_epoch <= epoch:
            payload[pct_field] = 0.0
            payload[reset_field] = None
    return payload
