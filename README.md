# token-usage

Lightweight statusbar tracker for Claude Code, ChatGPT Plus, Kimi Code, and OpenCode usage.

`token-usage` is a Python CLI for Linux users who want AI usage visible in a terminal or statusbar. It is designed for tiling window manager setups and dwmblocks-compatible bars, with provider-specific wrappers for clean statusbar integration.

## Features

- Tracks Claude Code, ChatGPT Plus, Kimi Code, OpenCode Zen, and OpenCode Go usage.
- Outputs compact statusbar text, multi-line detail views, and raw JSON.
- Uses Claude OAuth when available, then fresh statusline, then last-known-good real data, then a clearly-marked local JSONL estimate.
- Reads ChatGPT and Kimi usage from vendor web APIs using browser session cookies.
- Aggregates OpenCode usage from local SQLite history.
- Caches freshness per provider, so one slow or expired provider does not freeze the others.
- Ships drop-in statusbar wrapper scripts for combined or per-provider display.

## Requirements

- Python >=3.10
- Linux, POSIX environment
- A browser profile with active sessions for ChatGPT and Kimi when those providers are enabled
- Claude Code for Claude statusline integration
- OpenCode local SQLite history when OpenCode providers are enabled

## Quick Start

Clone → install → verify:

```sh
git clone https://github.com/panpeacemaker/token-usage.git
cd token-usage && ./install.sh
token-usage --version
token-usage --statusbar
```

You can also install from a local checkout with `pipx`:

```sh
pipx install .
```

## How it works

`token-usage` uses a hybrid source model. Each provider is read from the most reliable local or authenticated source available, then rendered into a compact format for statusbars.

### Claude Code

The Claude side uses a provenance-aware source chain. The priority is:

```text
OAuth → fresh statusline → LKG (valid) → local JSONL estimate → stale statusline → none/error
```

1. **OAuth.** Official usage API data wins when it is truly available. OAuth failures and 429 rate limits are error states, never silent `0%`.
2. **Fresh statusline.** Claude Code pipes live session JSON, including `rate_limits.five_hour` / `seven_day` percentages and reset times, to a `statusLine` command. `token-usage-statusline` captures that JSON to `~/.cache/token-usage/statusline.json`. The file must be younger than 600 seconds and have at least one valid quota window.
3. **LKG (last-known-good).** The most recent real OAuth/statusline reading, when its windows have not yet reset. Real numbers that are slightly old are far more trustworthy than the local estimate, so LKG is preferred over local and is marked **stale** (`c42%*`).
4. **Local JSONL estimate.** Aggregation of `~/.claude/projects/**/*.jsonl` plus OpenCode's Anthropic SQLite history. This is a *rough fallback estimate only* — Anthropic's 5h/7d percentages are computed by a formula we cannot see, and cache-read tokens dominate, so the local figure can be several times off the real dashboard. It is used only when no real source is available and is flagged as an **estimate** (`c42%?`), never presented as authoritative.
5. **Stale statusline.** Expired statusline data, marked stale, used only as a last resort.

`--detail` prints a `source:` line naming the winner and why other sources were rejected, for example `source: lkg (oauth: 429; statusline: stale)`.

### ChatGPT Plus and Kimi Code

ChatGPT Plus and Kimi Code usage are read directly from each vendor's web API using cookies pulled from your browser profile. Supported browsers are Firefox, Zen, Chrome, Chromium, and Brave. No tokens are stored on disk.

### OpenCode

OpenCode, sst/opencode, has no public quota or billing API, so usage is aggregated from the local SQLite history at `~/.local/share/opencode/opencode.db`. Results are filtered by `providerID`, `opencode` for Zen and `opencode-go` for Go, into fixed calendar windows.

Both OpenCode providers use the same window rule: 5-hour windows are aligned to fixed 5-hour UTC epoch blocks, weekly windows start Monday 00:00 UTC, and monthly windows start on the 1st at 00:00 UTC. Reset times are exact, provider-independent, and shown with `@` in the statusbar and `(fixed)` in `--detail`.

If an OpenCode provider has zero usage in both its 5-hour and weekly quota windows, it is rendered as idle: `e idle` or `g idle` in the statusbar, and a `⏼ idle` note in `--detail`. This is distinct from an active provider at `0%`. Monthly tokens are still shown when present.

Percentages are computed against the token limits configured in `[opencode]`. OpenCode is disabled by default.

### Cache behavior

The cache at `~/.cache/token-usage/summary.json` tracks freshness **per provider**. Running `sb-claude-usage` every statusbar tick will not freeze ChatGPT, Kimi, or OpenCode data. Each provider refreshes on its own TTL, and expired reset windows are rolled to 0% on render.

## Install

```sh
./install.sh
```

The installer:

- Installs the `token-usage` and `token-usage-statusline` console scripts.
- Installs four wrappers to `~/.local/bin/`: `sb-ai-usage`, `sb-claude-usage`, `sb-chatgpt-usage`, `sb-kimi-usage`.
- Adds, or surfaces a conflict with, a `statusLine` entry in `~/.claude/settings.json` pointing at `token-usage-statusline`.

## Usage

```sh
token-usage --statusbar                       # "c7%@07:00 o33%@02:35 k55%@03:20 e idle g20%@05:00"
token-usage --statusbar --only claude         # "c7%@07:00"
token-usage --statusbar --only chatgpt        # "o33%@02:35"
token-usage --statusbar --only kimi           # "k55%@03:20"
token-usage --statusbar --only opencode       # "e idle"
token-usage --statusbar --only opencode-go    # "g20%@05:00"
token-usage --statusbar --only claude,kimi    # "c7%@07:00 k55%@03:20"
token-usage --detail                          # multi-line detail (also honours --only)
token-usage --detail --only kimi              # Kimi section only, no other noise
token-usage --json                            # raw JSON (also honours --only)
token-usage --no-cache                        # bypass output cache
token-usage --version                         # print version
```

`--only` accepts canonical names and shorthand aliases:

| Provider | Canonical name | Aliases |
| --- | --- | --- |
| Claude | `claude` | `c` |
| ChatGPT | `chatgpt` | `o` |
| Kimi | `kimi` | `k` |
| OpenCode Zen | `opencode` | `e`, `oc`, `zen`, `opencode-zen` |
| OpenCode Go | `opencode-go` | `g`, `oc-go`, `go` |

### Compact format

```text
<letter><pct>%[*][@HH:MM]
```

| Field | Meaning |
| --- | --- |
| `<letter>` | `c` Claude, `o` ChatGPT, `k` Kimi, `e` OpenCode Zen, `g` OpenCode Go |
| `<pct>%` | **Highest valid quota window** (5-hour or weekly). Weekly pressure is never masked by an empty short window |
| `*` | Stale marker, Claude only, when serving cached statusline data |
| `@HH:MM` | Local time the driving window resets. Belongs to the same window that supplied `<pct>%`. OpenCode uses exact fixed-calendar resets |
| `idle` | OpenCode only. Zero usage in both 5-hour and weekly quota windows. Monthly tokens can still be shown in detail |

Segments are space-separated. `--detail` marks the driving window with `← bar`.

#### Pinning the driving window

By default, the statusbar segment for each provider shows the higher of its two windows (e.g. ChatGPT picks `primary` or `weekly` whichever is higher). To force a specific window — e.g. always show ChatGPT's `primary` to match the web UI — set `bar_window` in the provider's table of `config.toml`:

```toml
[openai]
bar_window = "primary"   # "max" | "primary" | "weekly"
```

Allowed values per provider: Claude `5h` / `7d`; ChatGPT `primary` / `weekly`; Kimi `5h` / `weekly`; OpenCode / OpenCode Go `5h` / `weekly` / `monthly`. `max` is the default and picks the highest of the configured windows. An invalid value falls back to `max`. If the pinned window is expired or missing, the segment falls back to `max` so the bar never shows stale data. The `--detail` `← bar` marker follows the same rule, so statusbar and detail always agree.

Examples:

| State | Output |
| --- | --- |
| 5-hour is the max | `c19%@02:10` |
| Weekly higher than 5-hour | `g20%@05:00` |
| Weekly maxed (== 100%) | `o100%@Tue21:28` |
| Stale Claude data | `c47%*@02:10` |
| Idle OpenCode provider | `e idle` |
| Provider unreachable | `k err` |

### Per-provider plugins

The repo ships four drop-in wrappers. Install puts them in `~/.local/bin/`. Wire each into your bar separately if you want one column per provider, or use `sb-ai-usage` for a single combined column.

| Script | Statusbar output | Left-click notification |
| --- | --- | --- |
| `sb-ai-usage` | `c7%@07:00 o33%@02:35 k55%@03:20 e idle g20%@05:00` | Enabled provider sections |
| `sb-claude-usage` | `c7%@07:00` | Claude detail + local JSONL stats |
| `sb-chatgpt-usage` | `o33%@02:35` | ChatGPT detail only |
| `sb-kimi-usage` | `k55%@03:20` | Kimi detail only |

`sb-ai-usage` and `sb-claude-usage` also bind middle-click to launch `claude-monitor` in a terminal if installed.

### `--only` filter

`--only PROVIDER[,PROVIDER...]` accepts canonical names and aliases listed above. It skips both the network fetch and the rendering for everything else. For example, `--detail --only kimi` shows only the Kimi section, with no "Claude unavailable" placeholder.

Pin the default set globally in `config.toml`:

```toml
[statusbar]
providers = ["claude", "kimi"]   # drop chatgpt from default --statusbar
```

### JSON output

The `_source` field in `--json` output shows which data source won the Claude lookup: `oauth`, `statusline`, `local`, `lkg`, `statusline-stale`, or `none`.

The `_source_detail` field carries the same provenance used by `--detail`, including rejected sources and reasons. LKG appears as `_source: "lkg"` and is marked stale.

## Config

Copy `config.example.toml` to `~/.config/token-usage/config.toml`.

```toml
[claude]
plan = "max5"
weekly_reset_weekday = 0      # 0=Mon ... 6=Sun
weekly_reset_hour_local = 22  # local timezone
bar_window = "max"            # max | 5h | 7d
cache_read_weight = 1.0       # effective = billed + cache-read × weight

[claude.limits.pro]            # optional override per plan
tokens_5h = 25000000
tokens_weekly = 560000000
messages_weekly = 250

[openai]
enabled = true
browser = "zen"                # firefox | zen | chrome | chromium | brave
bar_window = "max"            # max | primary | weekly

[kimi]
enabled = true
browser = "zen"
bar_window = "max"            # max | 5h | weekly

[opencode]
enabled = false                      # OpenCode Zen — letter `e`
provider_id = "opencode"
db_path = ""                         # empty = ~/.local/share/opencode/opencode.db
# windows are fixed calendar (5h block / week / month) — not configurable
primary_limit_tokens = 25000000      # required when enabled
weekly_limit_tokens = 560000000
monthly_limit_tokens = 0             # 0 = percentage hidden, tokens still shown
bar_window = "max"                  # max | 5h | weekly | monthly

[opencode-go]
enabled = false                      # OpenCode Go — letter `g`
primary_limit_tokens = 25000000      # required when enabled
weekly_limit_tokens = 560000000
monthly_limit_tokens = 0             # 0 = percentage hidden, tokens still shown
bar_window = "max"                  # max | 5h | weekly | monthly

[cache]
ttl_seconds = 300

[statusbar]
providers = ["claude", "chatgpt", "kimi", "opencode", "opencode-go"]
```

The Claude plan and limits matter for local JSONL. Local effective tokens are computed as billed tokens, `input + output + cache_creation`, plus `cache_read_weight × cache_read_tokens`. `--detail` shows the math as `effective: N (billed B + cache-read C × W)`. Weekly Claude `messages` count only real user/assistant API turns, deduped by message/request ID, with tool-call and sidechain records excluded.

ChatGPT and Kimi require you to be logged in to the respective web app in the configured browser profile. Cookies are read on every fetch, cached for `cache.ttl_seconds`, and nothing is stored on disk.

OpenCode requires `[opencode] enabled = true` and configured `*_limit_tokens`. No public API exposes the real Zen/Go quota, so the percentage is computed against your local budget. The provider only reads the SQLite history. The configured window sizes are kept as keys, but current behavior uses fixed calendar windows for both Zen and Go. If you also want OpenCode to be rendered without `--only`, append `"opencode"` or `"opencode-go"` to `[statusbar] providers`.

Example `--detail` excerpts:

```text
Claude (unknown) — unknown
━━━━━━━━━━━━━━━━━━━━━━━━
  source: local (oauth: 429; statusline: missing)
  ⏱  5-hour:    7.0%   resets Sun 07:00  ← bar
  📅 7-day:     3.4%   resets Mon 22:00

Local JSONL stats:
  current block: 8,000,000 tokens (+500,000 cache-read)
     effective: 8,500,000 (billed 8,000,000 + cache-read 500,000 × 1.0)
  this week: 42 msgs / 120,000,000 tokens (+10,000,000 cache-read)
     effective: 130,000,000 (billed 120,000,000 + cache-read 10,000,000 × 1.0)

OpenCode (opencode)
━━━━━━━━━━━━━━━━━━━━━━━━
  ⏼ idle — no activity in 5h/weekly windows
  monthly: —       resets Wed 00:00 (fixed)
     mo tokens:   123,456 / —
```

## Manual statusLine setup

If `install.sh` skipped the `settings.json` update because you already have a custom `statusLine`, add the writer manually:

```json
{
  "statusLine": {
    "type": "command",
    "command": "token-usage-statusline",
    "padding": 2
  }
}
```

The writer prints its own one-line status for Claude Code's UI and writes the cache file in the background.

## Uninstall

Remove the package and wrappers from `~/.local/bin/` and delete `~/.config/token-usage/` and `~/.cache/token-usage/` if desired.

## Credits

Inspired by these projects:

- [ccusage](https://github.com/ryoppippi/ccusage) by [@ryoppippi](https://github.com/ryoppippi) — Claude Code usage analyzer from local JSONL files (MIT)
- [AIQuotaBar](https://github.com/yagcioglutoprak/AIQuotaBar) by [@yagcioglutoprak](https://github.com/yagcioglutoprak) — macOS menu bar app for AI usage limits (MIT)
- [Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) by [@Maciek-roboblog](https://github.com/Maciek-roboblog) — real-time terminal monitor for Claude token usage (MIT)

## License

MIT. See `LICENSE` for details.
