from __future__ import annotations

from typing import Any


def _select_bar_window(
    data: dict,
    windows: list[tuple[str, str, str, str | None]],
    bar_window: str = "max",
) -> tuple[float, Any, str] | None:
    if bar_window != "max":
        for pct_field, reset_field, label, expired_field in windows:
            if label != bar_window:
                continue
            if expired_field and data.get(expired_field):
                break
            pct = data.get(pct_field)
            if pct is None:
                break
            try:
                return (float(pct), data.get(reset_field), label)
            except (TypeError, ValueError):
                break
    best = None
    for pct_field, reset_field, label, expired_field in windows:
        if expired_field and data.get(expired_field):
            continue
        pct = data.get(pct_field)
        if pct is None:
            continue
        try:
            pct_val = float(pct)
        except (TypeError, ValueError):
            continue
        reset = data.get(reset_field)
        if best is None or pct_val > best[0]:
            best = (pct_val, reset, label)
    return best
