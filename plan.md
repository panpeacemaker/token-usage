# plan.md — Data Reliability Fix Plan for token-usage

**Date:** 2026-06-10
**STATUS: ALL WAVES COMPLETE (2026-06-10).** 333 tests green (was 206). Waves 0–5 +
cleanup shipped; live QA verified statusbar/detail/json + `--only` isolation.
Residual: statusline source only available under Claude Code (hook never fires for
OpenCode sessions — by design, surfaced via `source:` provenance line).
**Verdict (Oracle-validated):** Targeted bug-fix waves, NOT redesign. The 3-layer
architecture (fetchers → cache/normalize → formatters) is sound. The trust gap comes
from **silent-wrong-data paths** and **ambiguous window/source semantics**, not from
structural failure. 206 tests pass because they assert shape/happy-path, not truth.

**Core contract to adopt (the one structural change):**
> Every displayed number must carry `source + fetched_at + freshness + window_basis +
> error_state`. Unknown/partial/schema-mismatch data must NEVER normalize to `0%`.
> Fail loud, mark stale clearly, stop displaying false zeros.

**Degrade policy (encode everywhere, consistently):**

| Situation | Statusbar | Detail |
|---|---|---|
| Fresh data | `c42%` | normal |
| Fetch fail, last-good within max-stale | `c~42%` (stale marker) | source + age + error |
| Schema/auth/config error, no safe stale | `c err` | exact error + provenance |
| Provider disabled/unconfigured | hidden | hidden |

---

## Wave 0 — Diagnose the Claude statusline path (INVESTIGATE FIRST)

**Symptom observed live:** active Claude session, yet source fell back to `oauth` and
5h showed `0.0%`. Statusline cache exists but is unused or rejected.

- [ ] Add provenance to `--detail`/`--json`: chosen Claude source, each rejected
      source, and per-window reject reason (`cli.py:_select_claude_source`).
- [ ] Verify `token-usage-statusline` writer actually fires during sessions
      (check `~/.cache/token-usage/statusline.json` mtime vs session activity).
      Note: user runs OpenCode (not Claude Code) — statusline hook may never fire
      for OpenCode sessions. If so, document it and make the fallback chain report
      WHY statusline was skipped.
- [ ] Test hypothesis: **B3** (`claude/statusline.py:69-72`) — `is_still_valid`
      rejects whole statusline when 5h window expired even if 7d still valid.
- [ ] Hypothesis: OAuth "success" returning empty/zero active window masks better
      statusline/local data. Check precedence logic in `_select_claude_source`.
- [ ] Hypothesis: account mismatch — OAuth token vs statusline vs local JSONL may
      describe different accounts/orgs. Surface account identity in `--json`.

**Exit criteria:** root cause of `c 0.0% via oauth during active session` identified
and written into this file before Wave 2 implementation.

## Wave 1 — Stop silent wrong data (HIGHEST TRUST IMPACT)

- [ ] **B7** `kimi/usage.py:67-72` — `_five_hour_window` returns `{}` on schema
      change → silent `k0%`. Fix: no matching window → return error state in
      `KimiUsage` (`available=False, error="schema: no 5h window"`), render `k err`.
- [ ] **B11** `_cookies.py:86` — unknown browser name silently falls back to
      Firefox cookies. Fix: `raise ValueError(f"unknown browser: {browser}")`;
      surface as provider error.
- [ ] **Audit ALL providers** for partial-API-response→zero normalization
      (Kimi is proven; check chatgpt_wham.py, oauth_usage.py the same way).
      Missing required field = error state, never 0.0.
- [ ] **B1+B6** (CRITICAL, same root) — OpenCode-Go lacks config identity.
      Add `opencode_go_db_path` + `opencode_go_provider_id` to `Config`
      (`config.py`), wire in `load()`, use in `cli.py:_fetch_opencode_go`
      (currently reuses `cfg.opencode_db_path` and hardcodes `"opencode-go"`).
- [ ] **B4** `_normalize.py:41-42` — `normalize_windows` mutates caller's dict.
      Fix: `payload = dict(payload)` at entry.
- [ ] **B8** `cli.py:200-236` — unselected providers still read+normalize+rewrite
      cache each run. Fix: pass through untouched (no normalize, no rewrite) for
      providers outside `selected`.
- [ ] **B9** `cli.py:281-284` — top-level `except Exception` prints `c err` with
      no traceback. Fix: keep `Exception` (not BaseException), print traceback to
      stderr; let KeyboardInterrupt/SystemExit propagate.

## Wave 2 — Claude correctness

- [ ] **B3** `claude/statusline.py:69-72` — per-WINDOW validity, not per-provider.
      Statusline valid if EITHER window unexpired; merge per-window: use statusline
      7d data even when its 5h window lapsed.
- [ ] **B2** `claude/local_summary.py:28` — `datetime.now().astimezone().tzinfo`
      is a fixed offset → weekly reset ±1h across DST. Fix: use
      `zoneinfo.ZoneInfo` (resolve local tz via `/etc/localtime` or `tzlocal`-style
      lookup; stdlib-only preferred).
- [ ] **B5** `claude/blocks.py:39` — gap start anchor wrong:
      `gap_start = last_ts + block_duration` → `current.start + block_duration`.
- [ ] **Local JSONL token semantics** — "this week: 290,992,999 tokens" counts
      cache-read tokens, wildly misleading vs plan limits. Fix: exclude cache-read
      from plan-usage totals OR label separately
      (`input+output / cache-read shown apart`) in `formatters/detail.py`.

## Wave 3 — Window semantics consistency (statusbar vs detail)

**Symptom:** statusbar `g0%` (5h) vs detail `4.1%` (weekly) — user perceives
disagreement.

- [ ] Statusbar segment % = `max(valid quota window pct)` per provider by default
      (so weekly pressure isn't masked by an empty 5h window).
- [ ] Detail marks which window drove the statusbar figure.
- [ ] Same basis rule applied to ALL providers in `formatters/statusbar.py`.

## Wave 4 — Rolling-window & cache semantics

- [x] **B13** `opencode/usage.py:75` — rolling `oldest_entry + window` displayed
      as fixed `@HH:MM` reset. Renamed semantics: detail shows `resets ~HH:MM (rolling)`,
      statusbar uses `~HH:MM` for rolling providers, JSON carries `window_kind: "rolling"`.
- [x] **B16** `opencode/usage.py:85-86` — removed 100% clamp; pct shows real value
      (e.g. `104%`) so over-limit is visible.
- [x] **B12** `cache.py:17-27` — added `_written_at` top-level stamp (CACHE_VERSION 10).
      `is_provider_fresh` and `read` reject any provider stamp or global `fetched_at`
      newer than `_written_at`. Negative age already handled by `0 <= age` in `_age_within`.
      **Residual risk:** if the system clock jumps backward after a write, `_age_within`
      returns stale (negative age) correctly; forward-then-backward jump is also caught.
      The `_written_at` check is defense-in-depth against manually tampered caches.

## Wave 5 — Regression suite that tests TRUTH, not shape

- [ ] Golden fixtures per provider/source: real captured API/DB payloads → exact
      expected statusbar + detail output.
- [ ] Schema-change failure tests: drop/rename a field in each provider fixture →
      MUST render `err`, never `0%`.
- [ ] DST-transition tests for `_next_weekly_reset` (CET↔CEST boundary dates).
- [ ] Cache immutability test: `normalize_windows` must not mutate input.
- [ ] `--only` isolation test: unselected providers' cache bytes unchanged.
- [ ] End-to-end consistency test: statusbar % == window marked in detail.
- [ ] Claude source-selection matrix test: every (statusline, oauth, local)
      availability combo → expected source + provenance fields.

## Cleanup (fold into waves where touched)

- [x] RN1: `config.example.toml` `tokens_5h` example already realistic (25M).
- [x] RN3: dead `codex_*` fields already removed from `ChatGPTUsage`.
- [x] B14: bare `except Exception` in `claude/oauth_usage.py:85` → narrowed to
      `(OSError, UnicodeDecodeError, ValueError)`.
- [x] B15: Kimi int/float `resetTime` now handled as unix seconds (ms if >1e12).
- [x] Bump `CACHE_VERSION` → 10 (`_written_at` field).

## Wave 0 findings

**Date:** 2026-06-10
**Investigator:** Sisyphus-Junior

### Root cause: why Claude fell back to `oauth` showing 5h=0.0%

1. **Statusline cache file is MISSING.**
   - `~/.cache/token-usage/statusline.json` does **not exist** (only `summary.json` exists).
   - The `token-usage-statusline` writer is a **Claude Code statusLine hook**.
   - The user primarily runs **OpenCode**, not Claude Code, so the hook **never fires**.
   - Therefore the statusline source is skipped with reason `"file missing"` before any window-validity check.

2. **OAuth silent-zero default (NEW BUG, distinct from B3).**
   - `claude/oauth_usage.py:_pct()` returns `0.0` when `utilization` is `None` or missing:
     ```python
     def _pct(obj) -> float:
         v = obj.get("utilization")
         return float(v) if v is not None else 0.0
     ```
   - If the Anthropic API omits the `five_hour` window or returns it without
     `utilization`, the CLI displays `0.0%` instead of an error.
   - **Evidence:** the `_pct` function has no "field missing" → error path.
     This is the same pattern as B7 (Kimi) and should be fixed in Wave 1.

3. **B3 confirmed but NOT the primary cause this time.**
   - `claude/statusline.py:is_still_valid` (L69-72) rejects the whole statusline
     when the 5h window expired even if the 7d window is still valid.
   - This is a real bug (proven by `test_is_still_valid_five_hour_expired_seven_day_not`),
     but it did not fire during the reported symptom because the statusline file
     was absent entirely.

### Evidence

- File listing:
  ```
  $ ls -la ~/.cache/token-usage/
  total 4
  drwxr-xr-x ... .
  drwxr-xr-x ... ..
  -rw-r--r--r-- ... summary.json
  # statusline.json is absent
  ```
- Current cache content (after provenance patch) shows:
  ```json
  "_source_detail": {
    "chosen": "oauth",
    "rejected": [{"source": "statusline", "reason": "file missing"}],
    "statusline_age_s": null
  }
  ```

### Scope impact

- **No fallback precedence change needed.** The chain behaves correctly when
  statusline is missing: statusline → OAuth → local → stale statusline → error.
- The 5h=0.0% value comes from OAuth (either real API value or silent-zero default).
  Provenance now surfaces `source: oauth (statusline: missing)` so this is no
  longer opaque.
- B3 should still be fixed in Wave 2 so that IF a statusline file exists and
  only the 5h window expired, the 7d data is still usable.

### Provenance implementation (delivered in Wave 0)

- `cli.py:_select_claude_source` now returns `_source_detail` dict:
  `{chosen, rejected: [{source, reason}], statusline_age_s}`.
- `--json` includes `_source_detail` automatically.
- `--detail` prints one line: `source: oauth (statusline: missing; local: ok)`.
- Tests added: `test_source_detail_display`, `test_source_detail_stale_display`,
  `test_source_detail_expired_display`, `test_source_detail_multiple_rejected`,
  plus provenance assertions in all existing hybrid tests.

---

## Execution notes

- Each wave = separate commit(s); tests green after every wave.
- Wave 0 findings may reorder Wave 2 items — update this file.
- Estimated effort: 1–2 days total (Oracle estimate, high confidence).
