# token-usage

`token-usage` replaces a buggy Claude/OpenAI usage tracker whose old Python script undercounted weekly usage by overwriting each JSONL file's accumulated entry and keeping only the last one.

It now ports ccusage's session-block logic for Claude and AIQuotaBar's ChatGPT Plus cookie-based tracking.

## Install

```sh
./install.sh
```

## Usage

```sh
token-usage --statusbar
token-usage --detail
token-usage --json
```

## Config

Copy `config.example.toml` to `~/.config/token-usage/config.toml`.

## Uninstall

Remove the package and wrappers from `~/.local/bin/` and delete `~/.config/token-usage/` and `~/.cache/token-usage/` if desired.

## Credits

- ccusage
- AIQuotaBar
- Claude-Code-Usage-Monitor
