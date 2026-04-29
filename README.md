# token-usage

Lightweight statusbar tracker for Claude Code, ChatGPT Plus, Kimi Code, and
OpenCode (sst/opencode) usage.

## How it works

The Claude side is a **hybrid of two sources**, neither of which hits a rate-limited API:

1. **Primary - Claude Code statusline JSON.** Claude Code pipes live session JSON
   (including `rate_limits.five_hour` / `seven_day` percentages and reset times)
   to a `statusLine` command. `token-usage-statusline` captures that JSON to
   `~/.cache/token-usage/statusline.json` on every message.
2. **Fallback - local JSONL aggregation.** When the statusline cache is absent
   or its tracked reset window has already expired, the CLI falls back to a
   ccusage-style aggregation of `~/.claude/projects/**/*.jsonl` (plus opencode
   SQLite history) using the plan limits in `config.toml`.

When both statusline and local JSONL are unavailable, the CLI falls back to
the OAuth usage API (`/api/usage`). The Claude source priority is:
**statusline → OAuth → local JSONL → stale statusline → error**.

ChatGPT Plus and Kimi Code usage are read directly from each vendor's web API
using cookies pulled from your browser profile (Firefox / Zen / Chrome /
Chromium / Brave). No tokens stored on disk.

OpenCode (sst/opencode) has no public quota/billing API, so usage is aggregated
from the local SQLite history at `~/.local/share/opencode/opencode.db` filtered
by `providerID` (`opencode` for Zen, `opencode-go` for Go) into a rolling 5-hour
and 7-day window. Percentages are computed against the token limits configured
in `[opencode]`. Disabled by default.

The cache (`~/.cache/token-usage/summary.json`) tracks freshness **per provider**:
running `sb-claude-usage` every statusbar tick will not freeze ChatGPT/Kimi/OpenCode
data — each provider refreshes on its own TTL, and expired reset windows are rolled
to 0% on render.

## Install

```sh
./install.sh
```

The installer:

- Installs the `token-usage` and `token-usage-statusline` console scripts.
- Installs four wrappers to `~/.local/bin/`:
  `sb-ai-usage`, `sb-claude-usage`, `sb-chatgpt-usage`, `sb-kimi-usage`.
- Adds (or surfaces a conflict with) a `statusLine` entry in
  `~/.claude/settings.json` pointing at `token-usage-statusline`.

## Usage

```sh
token-usage --statusbar                       # "c19%@02:10 o0%w100%@Tue21:28 k25%@02:54"
token-usage --statusbar --only claude         # "c19%@02:10"
token-usage --statusbar --only chatgpt        # "o0%w100%@Tue21:28"
token-usage --statusbar --only kimi           # "k25%@02:54"
token-usage --statusbar --only opencode       # "e12%@14:20"
token-usage --statusbar --only opencode-go    # "g25%@14:20"
token-usage --statusbar --only claude,kimi    # "c19%@02:10 k25%@02:54"
token-usage --detail                          # multi-line detail (also honours --only)
token-usage --detail --only kimi              # Kimi section only, no other noise
token-usage --json                            # raw JSON (also honours --only)
token-usage --no-cache                        # bypass output cache
token-usage --version                         # print version
```

`--only` accepts canonical names (`claude`, `chatgpt`, `kimi`, `opencode`,
`opencode-go`) and shorthand aliases (`c`, `o`, `k`, `e`/`oc`/`zen`/`opencode-zen`,
`g`/`oc-go`/`go`).

### Compact format

```
<letter><pct>%[*][@HH:MM][w<week_pct>%@<weekday><HH:MM>]
```

| Field | Meaning |
| --- | --- |
| `<letter>` | `c` Claude, `o` ChatGPT, `k` Kimi, `e` OpenCode Zen, `g` OpenCode Go |
| `<pct>%` | Current short-window usage (5-hour for Claude/Kimi/OpenCode, primary for ChatGPT) |
| `*` | Stale marker — Claude only, when serving cached statusline data |
| `@HH:MM` | Local time the short window resets. Hidden when `week_pct >= 100` (irrelevant once weekly is exhausted) |
| `w<week_pct>%@<weekday><HH:MM>` | Weekly warning suffix. Only appears when weekly hits the **80% threshold** |

Segments are space-separated. Examples:

| State | Output |
| --- | --- |
| Healthy weekly (< 80%) | `c19%@02:10` |
| Weekly warning triggered | `c30%@02:10w85%@Mon22:00` |
| Weekly maxed (== 100%) | `o0%w100%@Tue21:28` |
| Stale Claude data | `c47%*@02:10` |
| Provider unreachable | `k err` |

### Per-provider plugins

The repo ships four drop-in wrappers. Install puts them in `~/.local/bin/`.
Wire each into your bar separately if you want one column per provider, or
use `sb-ai-usage` for a single combined column.

| Script | Statusbar output | Left-click (notification) |
| --- | --- | --- |
| `sb-ai-usage` | `c19%@02:10 o0%w100%@Tue21:28 k25%@02:54` | All three sections |
| `sb-claude-usage` | `c19%@02:10` | Claude detail + local JSONL stats |
| `sb-chatgpt-usage` | `o0%w100%@Tue21:28` | ChatGPT detail only |
| `sb-kimi-usage` | `k25%@02:54` | Kimi detail only |

`sb-ai-usage` and `sb-claude-usage` also bind middle-click to launch
`claude-monitor` in a terminal if installed.

### `--only` filter

`--only PROVIDER[,PROVIDER...]` accepts `claude`, `chatgpt`, `kimi` (or
single-letter aliases `c`, `o`, `k`). It skips both the network fetch *and*
the rendering for everything else — `--detail --only kimi` shows only the
Kimi section, no "Claude unavailable" placeholder.

Pin the default set globally in `config.toml`:

```toml
[statusbar]
providers = ["claude", "kimi"]   # drop chatgpt from default --statusbar
```

### JSON output

The `_source` field in `--json` output shows which data source won the
Claude lookup: `statusline`, `oauth`, `local`, `statusline-stale`, or `none`.

## Config

Copy `config.example.toml` to `~/.config/token-usage/config.toml`.

```toml
[claude]
plan = "max5"
weekly_reset_weekday = 0      # 0=Mon ... 6=Sun
weekly_reset_hour_local = 22  # local timezone

[claude.limits.pro]            # optional override per plan
tokens_5h = 25000000
tokens_weekly = 560000000
messages_weekly = 250

[openai]
enabled = true
browser = "zen"                # firefox | zen | chrome | chromium | brave

[kimi]
enabled = true
browser = "zen"

[opencode]
enabled = false                      # OpenCode Zen — letter `e`
provider_id = "opencode"
db_path = ""                         # empty = ~/.local/share/opencode/opencode.db
primary_window_hours = 5
weekly_window_days = 7
primary_limit_tokens = 25000000      # required when enabled
weekly_limit_tokens = 560000000

[opencode-go]
enabled = false                      # OpenCode Go — letter `g`
primary_window_hours = 5
weekly_window_days = 7
primary_limit_tokens = 25000000      # required when enabled
weekly_limit_tokens = 560000000

[cache]
ttl_seconds = 300

[statusbar]
providers = ["claude", "chatgpt", "kimi", "opencode", "opencode-go"]
```

The Claude plan and limits only matter when falling back to local JSONL.
When the statusline cache is active, percentages come straight from Anthropic.

ChatGPT and Kimi require you to be logged in to the respective web app in
the configured browser profile. Cookies are read on every fetch (cached for
`cache.ttl_seconds`); nothing is stored on disk.

OpenCode requires `[opencode] enabled = true` and configured `*_limit_tokens`
(no public API exposes the real Zen/Go quota, so the percentage is computed
against your local budget). The provider only reads the SQLite history; if you
also want OpenCode to be rendered without `--only`, append `"opencode"` to
`[statusbar] providers`.

## Manual statusLine setup

If `install.sh` skipped the `settings.json` update because you already have a
custom `statusLine`, add the writer manually:

```json
{
  "statusLine": {
    "type": "command",
    "command": "token-usage-statusline",
    "padding": 2
  }
}
```

The writer prints its own one-line status for Claude Code's UI and writes the
cache file in the background.

## Uninstall

Remove the package and wrappers from `~/.local/bin/` and delete
`~/.config/token-usage/` and `~/.cache/token-usage/` if desired.

## Credits

- ccusage
- AIQuotaBar
- Claude-Code-Usage-Monitor
