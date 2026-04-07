#!/bin/sh
set -eu

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_BIN="${HOME}/.local/bin"
BACKUP_DIR="${LOCAL_BIN}/.token-usage-backup"

mkdir -p "$BACKUP_DIR" "$LOCAL_BIN"

echo "==> Backing up old scripts to $BACKUP_DIR"
for f in ai-usage-calculator sb-ai-usage; do
    if [ -e "$LOCAL_BIN/$f" ] && [ ! -L "$LOCAL_BIN/$f" ]; then
        cp "$LOCAL_BIN/$f" "$BACKUP_DIR/$f.$(date +%Y%m%d-%H%M%S)"
    fi
    rm -f "$LOCAL_BIN/$f"
done

echo "==> Installing token-usage package"
python3 -m pip install --user --upgrade "$REPO_DIR"

echo "==> Installing sb-ai-usage wrapper"
install -m 0755 "$REPO_DIR/scripts/sb-ai-usage" "$LOCAL_BIN/sb-ai-usage"

echo "==> Done"
echo
echo "Next steps:"
echo "  1. Verify: $LOCAL_BIN/sb-ai-usage"
echo "  2. Verify: token-usage --statusbar"
echo "  3. Refresh dwmblocks: pkill -RTMIN+22 dwmblocks"
