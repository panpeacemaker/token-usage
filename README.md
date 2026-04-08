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

No OAuth usage endpoint. No 429s. No rate-limit backoff.

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
token-usage --statusbar   # compact: "| C 23% w 41% @14:30 "
token-usage --detail      # multi-line detail
token-usage --json        # raw JSON
token-usage --no-cache    # bypass output cache
```

The `_source` field in `--json` output shows which data source won:
`statusline`, `local`, `statusline-stale`, or `none`.

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
