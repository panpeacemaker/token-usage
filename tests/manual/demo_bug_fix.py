from __future__ import annotations

import json
from pathlib import Path

from token_usage.claude.reader import load_entries


def main() -> int:
    entries = load_entries()
    new_total = sum(e.total_tokens for e in entries)

    projects = Path.home() / ".claude" / "projects"
    old_total = 0
    for f in projects.rglob("*.jsonl"):
        last = 0
        try:
            with open(f, encoding="utf-8", errors="replace") as fp:
                for line in fp:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    msg = d.get("message", {})
                    if not isinstance(msg, dict) or "usage" not in msg:
                        continue
                    u = msg["usage"]
                    tok = (
                        u.get("input_tokens", 0)
                        + u.get("output_tokens", 0)
                        + u.get("cache_creation_input_tokens", 0)
                        + u.get("cache_read_input_tokens", 0)
                    )
                    if tok > 0:
                        last = tok
            old_total += last
        except Exception:
            pass

    print(f"Files scanned:     {sum(1 for _ in projects.rglob('*.jsonl')):,}")
    print(f"Deduped entries:   {len(entries):,}")
    print(f"Old broken algo:   {old_total:,} ({old_total/1e6:.1f}M tokens)")
    print(f"New fixed algo:    {new_total:,} ({new_total/1e9:.2f}B tokens)")
    print(f"Undercount fixed:  {new_total / max(old_total, 1):.1f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
