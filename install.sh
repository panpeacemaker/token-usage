#!/bin/sh
set -eu

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_BIN="${HOME}/.local/bin"
BACKUP_DIR="${LOCAL_BIN}/.token-usage-backup"
SETTINGS_FILE="${HOME}/.claude/settings.json"

mkdir -p "$BACKUP_DIR" "$LOCAL_BIN"

echo "==> Backing up old scripts to $BACKUP_DIR"
for f in ai-usage-calculator sb-ai-usage sb-claude-usage sb-chatgpt-usage sb-kimi-usage sb-opencode-usage sb-opencode-go-usage; do
    if [ -e "$LOCAL_BIN/$f" ] && [ ! -L "$LOCAL_BIN/$f" ]; then
        cp "$LOCAL_BIN/$f" "$BACKUP_DIR/$f.$(date +%Y%m%d-%H%M%S)"
    fi
    rm -f "$LOCAL_BIN/$f"
done

echo "==> Installing token-usage package"
if python3 -m pip show token-usage >/dev/null 2>&1; then
    echo "   removing legacy pip --user install"
    python3 -m pip uninstall -y --break-system-packages token-usage 2>/dev/null \
        || python3 -m pip uninstall -y token-usage 2>/dev/null \
        || true
fi

if command -v pipx >/dev/null 2>&1; then
    pipx install --force "$REPO_DIR"
else
    python3 -m pip install --user --break-system-packages --upgrade "$REPO_DIR" 2>/dev/null \
        || python3 -m pip install --user --upgrade "$REPO_DIR"
fi

echo "==> Installing sb-* wrappers"
install -m 0755 "$REPO_DIR/scripts/sb-ai-usage"          "$LOCAL_BIN/sb-ai-usage"
install -m 0755 "$REPO_DIR/scripts/sb-claude-usage"      "$LOCAL_BIN/sb-claude-usage"
install -m 0755 "$REPO_DIR/scripts/sb-chatgpt-usage"     "$LOCAL_BIN/sb-chatgpt-usage"
install -m 0755 "$REPO_DIR/scripts/sb-kimi-usage"        "$LOCAL_BIN/sb-kimi-usage"
install -m 0755 "$REPO_DIR/scripts/sb-opencode-usage"    "$LOCAL_BIN/sb-opencode-usage"
install -m 0755 "$REPO_DIR/scripts/sb-opencode-go-usage" "$LOCAL_BIN/sb-opencode-go-usage"

echo "==> Configuring Claude Code statusLine"
python3 - "$SETTINGS_FILE" <<'PY'
import json
import os
import shutil
import sys
import time
from pathlib import Path

settings_path = Path(sys.argv[1])
writer_cmd = "token-usage-statusline"

settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        print(f"WARNING: {settings_path} is not valid JSON, leaving untouched")
        sys.exit(0)

existing = settings.get("statusLine")
if existing and existing.get("command") != writer_cmd:
    print(f"NOTE: existing statusLine found: {existing}")
    print(f"      to use token-usage, set command to: {writer_cmd}")
    print("      skipping automatic update to preserve your config")
    sys.exit(0)

settings.setdefault("statusLine", {})
settings["statusLine"] = {"type": "command", "command": writer_cmd, "padding": 2}

settings_path.parent.mkdir(parents=True, exist_ok=True)
if settings_path.exists():
    backup = settings_path.with_suffix(f".json.bak.{int(time.time())}")
    shutil.copy2(settings_path, backup)
    print(f"   backed up existing settings to {backup}")

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print(f"   updated {settings_path}")
PY

echo "==> Done"
echo
echo "Next steps:"
echo "  1. Verify: $LOCAL_BIN/sb-ai-usage"
echo "  2. Verify: token-usage --statusbar"
echo "  3. Start a Claude Code session to populate statusline cache"
echo "  4. Refresh dwmblocks: pkill -RTMIN+22 dwmblocks"
