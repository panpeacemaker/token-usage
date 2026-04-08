from __future__ import annotations

import json
import sys
from pathlib import Path

from .cache import CACHE_DIR

STATUSLINE_CACHE_FILE = CACHE_DIR / "statusline.json"


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload)
    tmp.replace(path)


def _format_status(data: dict) -> str:
    model = (data.get("model") or {}).get("display_name") or "?"
    parts: list[str] = [f"[{model}]"]

    rate = data.get("rate_limits") or {}
    five = (rate.get("five_hour") or {}).get("used_percentage")
    seven = (rate.get("seven_day") or {}).get("used_percentage")
    if five is not None:
        parts.append(f"5h {int(round(float(five)))}%")
    if seven is not None:
        parts.append(f"7d {int(round(float(seven)))}%")

    ctx = (data.get("context_window") or {}).get("used_percentage")
    if ctx is not None:
        parts.append(f"ctx {int(float(ctx))}%")

    cost = (data.get("cost") or {}).get("total_cost_usd")
    if cost is not None:
        try:
            parts.append(f"${float(cost):.2f}")
        except (TypeError, ValueError):
            pass

    return " | ".join(parts)


def main(argv: list[str] | None = None) -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print("[token-usage] empty stdin", file=sys.stderr)
            return 1
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[token-usage] invalid JSON: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"[token-usage] stdin read failed: {e}", file=sys.stderr)
        return 1

    try:
        _atomic_write(STATUSLINE_CACHE_FILE, json.dumps(data))
    except OSError as e:
        print(f"[token-usage] cache write failed: {e}", file=sys.stderr)

    print(_format_status(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
