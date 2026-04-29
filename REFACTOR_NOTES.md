# token-usage Refactor Notes

**Last updated:** 2026-04-29
**Status:** All waves complete — 201 tests passing
**Version:** 0.2.0

---

## Wave 9 — OpenCode Go provider (2026-04-29) ✅

Added `opencode-go` as a parallel provider next to `opencode` (Zen). Same SQLite
backend, different `providerID` filter. Statusbar letter: `g`.

- `[opencode-go]` config section (mirrors `[opencode]` schema except no
  `provider_id` / `db_path` — those are fixed and inherited respectively).
- Aliases: `g`, `oc-go`, `go`, `opencode-go`.
- `_build_summary` now returns 5-tuple `(summary, openai, kimi, opencode, opencode_go)`.
- `cache.py` bumped to `CACHE_VERSION = 9` to add `opencode_go` payload key.
- New `format_compact(..., opencode_go=...)`, new `_opencode_section(label="OpenCode Go")`.
- Tests: aliases, alongside-provider rendering, `--only opencode-go`, `--only g`.

---

## Wave 8 — Per-provider cache freshness + OpenCode provider (2026-04-29) ✅

**Bug fixed:** `--only claude` (e.g. via `sb-claude-usage` running every statusbar tick)
poisoned the cache by rewriting the global `fetched_at` while keeping arbitrarily-old
ChatGPT/Kimi payloads. The TTL gate then never invalidated those payloads. End state:
ChatGPT could show a weekly window that reset 8+ hours ago at 100%.

**Fix:**
- Cache bumped to `CACHE_VERSION = 8`. New `_provider_fetched_at: dict[str, float]`
  tracks freshness independently per provider.
- `cache.write(payload, fetched_providers={...})` now stamps **only** the providers
  actually fetched on this tick, preserving stale stamps for the rest.
- New `cache.is_provider_fresh(payload, name, ttl)` is the per-provider TTL gate;
  `cli._build_summary` calls it instead of a single global gate.
- New `_normalize.normalize_windows(payload, fields, now=...)` rolls expired
  `*_pct` / `*_reset_at` pairs to `0.0 / None` on both fetch and cache-read paths.
  Applied to ChatGPT (`primary`/`weekly`/`review`), Kimi (`primary`/`weekly`),
  and OpenCode (`primary`/`weekly`).

**New provider:** `opencode` (`e` letter). No public OpenCode quota API exists, so
usage is aggregated from `~/.local/share/opencode/opencode.db` filtered by
`providerID` into a 5h + 7d rolling window. Percentage = tokens / `*_limit_tokens`
(configurable). Opt-in via `[opencode] enabled = true`.

**Files touched:**
- `src/token_usage/cache.py` — `CACHE_VERSION = 8`, `provider_fetched_at`,
  `is_provider_fresh`, `write(payload, fetched_providers=...)`.
- `src/token_usage/_normalize.py` — new helper.
- `src/token_usage/cli.py` — per-provider TTL loop, `_fetch_opencode`,
  `_build_summary` returns 4-tuple `(summary, openai, kimi, opencode)`.
- `src/token_usage/config.py` — `[opencode]` schema, `ALL_PROVIDERS` includes
  `"opencode"`, aliases `e`/`oc`/`zen`/`opencode-zen`.
- `src/token_usage/opencode/{__init__.py,usage.py}` — `fetch_opencode` SQLite reader.
- `src/token_usage/formatters/{statusbar.py,detail.py,json_out.py}` — new `e` segment.
- `tests/test_cache.py` — v7 rejection, per-provider freshness, write semantics.
- `tests/test_normalize_windows.py` — new (9 tests).
- `tests/test_opencode_usage_provider.py` — new (12 tests).
- `tests/test_only_filter.py` — regression test
  `test_only_claude_does_not_restamp_chatgpt_or_kimi`, opencode aliases & wiring.
- `tests/test_statusbar.py`/`test_detail.py`/`test_json_out.py` — `e` segment.
- `README.md` / `config.example.toml` — OpenCode docs + `[opencode]` example.

**Migration:** v7 caches are rejected on load; the next fetch rebuilds clean v8.

---

## What's Been Done

### Wave 0 — Infrastructure ✅

- [x] **0.1**: Populated `tests/conftest.py` with shared fixtures (`make_usage_entry`, `make_jsonl_record`, `write_jsonl`, `utc_now` fixture, factory fixtures)
- [x] **0.2**: Added `[tool.ruff]`, `[tool.pytest.ini_options]`, `[tool.hatch.build.targets.sdist]` to `pyproject.toml` (added ruff dependency, classifiers, keywords)
- [x] **0.3**: Created empty `src/token_usage/py.typed` marker for PEP 561

**Note:** Wave 0 is purely infrastructure — doesn't affect runtime behavior. Fixtures in `conftest.py` exist but aren't yet used in existing test files.

---

## What Has to Be Done

### 🚨 HIGH PRIORITY — Wave 1.1: Stale Marker Bug Fix

**Critical bug:** `formatters/statusbar.py:31` and `formatters/detail.py:39,43-56` check `_stale`, `_stale_reason`, `_fetched_at` — but `cli._build_summary` **NEVER sets these fields**. The stale display is silently lost.

**Root cause:** Git archaeology confirmed:
- `74c42d3` — introduced `_stale`, `_stale_reason`, `_fetched_at`, `_retry_at` fields
- `96ed19d` — removed the producer that set these fields
- `86bb621` — restored OAuth but NOT the stale machinery

**Fix required in `cli._build_summary`:**

After source selection (around line 52-53 where `source = "statusline-stale"`), add:

```python
if source == "statusline-stale":
    summary["_stale"] = True
    summary["_stale_reason"] = f"oauth failed ({oauth_error}); no local data; using expired statusline"
    # _fetched_at: use statusline cache file mtime
    try:
        from .claude import statusline as sl_mod
        summary["_fetched_at"] = sl_mod.STATUSLINE_CACHE_FILE.stat().st_mtime
    except OSError:
        pass
    # Do NOT set _retry_at — Retry-After header parsing was dropped and no longer exists
```

**⚠️ MANDATORY — CACHE_VERSION bump:** Must bump `CACHE_VERSION` from 5 to 6 in `cache.py:10` in the **same commit** as Wave 1.1. Without it, pre-fix `summary.json` (up to 300s TTL) masks the fix — old cache returned verbatim, stale marker still absent.

**⚠️ CRITICAL:** Existing test `test_statusbar.test_stale_marker` validates dead code by manually injecting `_stale=True` — it should pass before AND after the fix (behavior doesn't change for manually-injected stale).

---

### 🚨 HIGH PRIORITY — Wave 1.2: Delete Unused `codex_*` Fields

**Bug:** `chatgpt_wham.py:108-109`:
```python
codex_pct=pct(primary), codex_reset_at=reset(primary)
```
- These are copy-paste errors
- Fields never read by any formatter (verified via grep)
- Should delete from `ChatGPTUsage` dataclass (lines 17-18):
  ```python
  codex_pct: float = 0.0
  codex_reset_at: int | None = None
  ```

**Note:** No grep for `codex_pct` in tests — safe to delete without test updates.

---

### HIGH PRIORITY — Wave 1.3: Fix README.md:18

**Bug:** README.md line 18 says "No OAuth usage endpoint" but OAuth was restored in commit `86bb621`.

**Fix:** Update README to reflect that OAuth is now a data source option.

---

### HIGH PRIORITY — Wave 1.4: Fix `config.example.toml`

**Bug:** `tokens_5h = 19000` but `limits.py:24` default is `25_000_000` — broken example (1000x too small).

**Fix:** Update to `tokens_5h = 25000000`.

---

### HIGH PRIORITY — Wave 1.5: Narrow `config.load` Exceptions

**Bug:** `config.load:34` catches bare `except Exception` → silently returns defaults on any TOML parse error.

**Fix:**
1. Narrow to `except tomllib.TOMLDecodeError`
2. Print warning to stderr
3. Add malformed-TOML test in `test_cli_hybrid.py`

---

### MEDIUM PRIORITY — Wave 1.6: Improve Error Message

**Bug:** `cli.main:85-86` catches bare `Exception` and loses the stack trace.

**Fix:** Add `type(e).__name__` to error message:
```python
print(f"err: {type(e).__name__}: {e}", file=sys.stderr)
```

---

### MEDIUM PRIORITY — Wave 2: Type Safety & Polish

| # | Task | Status |
|---|---|---|
| 2.1 | Define `SummaryDict = TypedDict` in `claude/_types.py` | ⬜ |
| 2.2 | Define `SourceName = Literal[...]` in `claude/_constants.py` | ⬜ |
| 2.3 | Update formatter signatures to use `SummaryDict` | ⬜ |
| 2.4 | Move `import time` to module level in `detail.py` | ⬜ |
| 2.5 | Add `--version` flag to CLI using `__version__` | ⬜ |
| 2.6 | Add docstrings to public functions in all modules | ⬜ |

---

### HIGH PRIORITY — Wave 3: Extract Helper Functions

**Oracle-approved design** (NOT chain-of-responsibility):

```python
def _build_summary(cfg: cfg_mod.Config) -> tuple[dict, dict | None]:
    fresh = cache.read(cfg.cache_ttl_seconds)
    if fresh is not None:
        return fresh.get("summary", {}), fresh.get("openai")

    ctx = _gather_sources(cfg)          # parallel fetch
    claude_usage, source, stale_info = _select_claude_source(ctx)  # selection
    summary = _build_summary_dict(claude_usage, source, stale_info, ctx.local_detail)

    openai_data = _fetch_openai(cfg)
    cache.write({"summary": summary, "openai": openai_data})
    return summary, openai_data
```

| # | Task | Status |
|---|---|---|
| 3.1 | Extract `_gather_sources(cfg) -> SourceContext` from `_build_summary` | ⬜ |
| 3.2 | Extract `_select_claude_source(ctx) -> (usage, source, stale_info)` | ⬜ |
| 3.3 | Extract `_build_summary_dict(...)` helper | ⬜ |
| 3.4 | Verify all 13 `test_cli_hybrid.py` tests still pass | ⬜ |

**Key constraint:** `_select_claude_source` must return `oauth_error` so the "none" path can build the error message.

---

### MEDIUM PRIORITY — Wave 5: Quality & Robustness

| # | Task | Status |
|---|---|---|
| 5.1 | `opencode_reader`: replace `LIKE '%\"role\":\"assistant\"%'` with `json_extract()` for JSON filtering | ⬜ |
| 5.3 | `_next_weekly_reset`: narrow exceptions, print warning | ⬜ |

**Dropped:**
- ~~5.2~~ — Cross-source dedup (no reliable dedup key exists; opencode uses SQLite row IDs, JSONL uses Anthropic UUIDs)
- ~~5.4~~ — Logging conversion (overkill for CLI)

---

### MEDIUM PRIORITY — Wave 6: Test Coverage Gaps

**No tests exist for:**
| # | Module | Status |
|---|---|---|
| 6.1 | `test_cli_main.py`: dispatch tests (--statusbar/--detail/--json/--version/--no-cache) | ⬜ |
| 6.3 | `test_detail.py`: stale/local/opus/sonnet scenarios | ⬜ |
| 6.4 | `test_json_out.py` | ⬜ |
| 6.5 | `test_chatgpt_wham.py`: mocked cookies + responses | ⬜ |
| 6.7 | `test_cache.py`: TTL, versioning, atomic write, stale reject | ⬜ |

**Pre-existing test gaps (no action needed):**
- `test_opencode_reader.py` — already exists (6 tests)
- `test_statusline_writer.py` — already exists (6 tests)

---

### LOW PRIORITY — Wave 7: Documentation & Metadata

| # | Task | Status |
|---|---|---|
| 7.1 | Update README architecture diagram | ⬜ |
| 7.2 | Add `CHANGELOG.md` | ⬜ |
| 7.3 | `pyproject.toml` metadata (authors, urls) | ⬜ |

---

### 🚨 FINAL — Run Full Test Suite

**Must verify:** 56+ tests pass with no regressions after each wave.

---

## Key Constraints

1. **No scope reduction** — don't drop features
2. **No partial completion** — each wave must be complete
3. **No deleting failing tests** — never delete tests to make things pass
4. **CACHE_VERSION bump must accompany Wave 1.1** — same commit, non-negotiable
5. **Don't set `_retry_at`** in Wave 1.1 — Retry-After parsing was dropped and no longer exists

---

## File Map

### Source Files (20)
| File | Purpose |
|------|---------|
| `src/token_usage/cli.py` | Main entry, `_build_summary` fallback chain (100 LOC) — **NEEDS Wave 1.1, 1.6, 3** |
| `src/token_usage/__init__.py` | `__version__ = "0.1.0"` |
| `src/token_usage/__main__.py` | Thin wrapper |
| `src/token_usage/config.py` | TOML config loader (47 LOC) — **NEEDS Wave 1.5** |
| `src/token_usage/cache.py` | Atomic write, TTL, versioned cache (46 LOC) — **NEEDS CACHE_VERSION bump** |
| `src/token_usage/statusline_writer.py` | stdin→cache+stdout (69 LOC) |
| `src/token_usage/claude/models.py` | `UsageEntry`, `SessionBlock`, `ClaudeUsage` dataclasses (58 LOC) — **NEEDS Wave 1.2** |
| `src/token_usage/claude/reader.py` | JSONL reader with dedup (87 LOC) |
| `src/token_usage/claude/opencode_reader.py` | SQLite reader (80 LOC) — **NEEDS Wave 5.1** |
| `src/token_usage/claude/blocks.py` | 5h session blocks (54 LOC) |
| `src/token_usage/claude/limits.py` | Plan limits (40 LOC) |
| `src/token_usage/claude/aggregator.py` | summarize() dict (66 LOC) |
| `src/token_usage/claude/statusline.py` | Statusline cache reader (63 LOC) |
| `src/token_usage/claude/local_summary.py` | Compose reader+aggregator+weekly reset (101 LOC) |
| `src/token_usage/claude/oauth_usage.py` | OAuth API call (134 LOC) |
| `src/token_usage/claude/__init__.py` | Re-exports |
| `src/token_usage/formatters/statusbar.py` | Compact statusbar (59 LOC) — reads `_stale` |
| `src/token_usage/formatters/detail.py` | Multi-line detail (111 LOC) — reads `_stale` |
| `src/token_usage/formatters/json_out.py` | Raw JSON (14 LOC) |
| `src/token_usage/openai_chat/chatgpt_wham.py` | ChatGPT usage (112 LOC) — **NEEDS Wave 1.2** |

### Config/Install Files
| File | Status |
|------|--------|
| `pyproject.toml` | ✅ Wave 0.2 done |
| `config.example.toml` | ❌ Needs Wave 1.4 |
| `README.md` | ❌ Needs Wave 1.3 |
| `install.sh` | OK |
| `scripts/sb-ai-usage` | OK |

### Test Files (56 tests, all passing)
| File | Tests | Status |
|------|-------|--------|
| `tests/conftest.py` | — | ✅ Wave 0.1 done |
| `tests/test_cli_hybrid.py` | 13 | Key for fallback chain |
| `tests/test_statusbar.py` | 8 | Includes `test_stale_marker` (validates dead code) |
| `tests/test_statusline.py` | 10 | |
| `tests/test_local_summary.py` | 4 | |
| `tests/test_reader.py` | 3 | |
| `tests/test_blocks.py` | 4 | |
| `tests/test_aggregator.py` | 2 | |
| `tests/test_limits.py` | 2 | |
| `tests/test_statusline_writer.py` | 6 | |
| `tests/test_oauth_usage.py` | 7 | |
| `tests/test_opencode_reader.py` | 6 | |
| `tests/fixtures/` | 3 JSONL fixtures | |
