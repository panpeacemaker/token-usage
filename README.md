# token-usage

Lightweight statusbar tracker for Claude Code and ChatGPT Plus usage.

## How it works

The Claude side is a **hybrid of two sources**, neither of which hits a rate-limited API:

1. **Primary - Claude Code statusline JSON.** Claude Code pipes live session JSON
   (including `rate_limits.five_hour` / `seven_day` percentages and reset times)
   to a `statusLine` command. `token-usage-statusline` captures that JSON to
   `~/.cache/token-usage/statusline.json` on every message.
2. **Fallback - local JSONL aggregation.** When the statusline cache is absent
   or its tracked reset window has already expired, the CLI falls back to a
   ccusage-style aggregation of `~/.claude/projects/**/*.jsonl` using the
   plan limits in `config.toml`.

When both statusline and local JSONL are unavailable, the CLI falls back to
the OAuth usage API (`/api/usage`). The source priority is:
**statusline → OAuth → local JSONL → stale statusline → error**.

## Install

```sh
./install.sh
```

The installer:

- Installs the `token-usage` and `token-usage-statusline` console scripts.
- Installs the `sb-ai-usage` wrapper to `~/.local/bin/`.
- Adds (or surfaces a conflict with) a `statusLine` entry in
  `~/.claude/settings.json` pointing at `token-usage-statusline`.

## Usage

```sh
token-usage --statusbar                  # compact: "| C 23% w 41% @14:30 | O 0% @19:54 | K 0% @21:54 "
token-usage --statusbar --only claude    # just one provider, bare (no leading "| ")
token-usage --statusbar --only chatgpt   # ditto for chatgpt
token-usage --statusbar --only kimi      # ditto for kimi
token-usage --statusbar --only claude,kimi   # subset
token-usage --detail                     # multi-line detail (also honours --only)
token-usage --json                       # raw JSON (also honours --only)
token-usage --no-cache                   # bypass output cache
token-usage --version                    # print version
```

`--only PROVIDER[,PROVIDER...]` accepts `claude`, `chatgpt`, `kimi` (or single-letter
`c`, `o`, `k`) and skips both the network fetch *and* the rendering for everything else.
When `--only` selects exactly one provider the leading `| ` / trailing space framing is
dropped, so each invocation can be wired up as its own bar plugin.

The `_source` field in `--json` output shows which data source won the Claude lookup:
`statusline`, `oauth`, `local`, `statusline-stale`, or `none`.

### One plugin per provider

The repo ships three drop-in wrappers (`scripts/sb-{claude,chatgpt,kimi}-usage`) modelled
on `sb-ai-usage`. Install puts them in `~/.local/bin/`. Wire each into your bar
separately if you want one column per provider instead of a combined string:

| Script | Output |
| --- | --- |
| `sb-claude-usage`  | `C 56% @21:10` |
| `sb-chatgpt-usage` | `O 0% w 100% @00:09` |
| `sb-kimi-usage`    | `K 0% @21:54` |

Or pin the default set globally in `config.toml`:

```toml
[statusbar]
providers = ["claude", "kimi"]   # drop chatgpt from default --statusbar
```

## Config

Copy `config.example.toml` to `~/.config/token-usage/config.toml`.

The Claude plan and limits only matter when falling back to local JSONL.
When the statusline cache is active, percentages come straight from Anthropic.

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
