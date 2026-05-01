#!/bin/bash
# Render the LaunchAgent plist template with this user's paths and install it.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$SCRIPT_DIR/granola-sync.plist.template"
LABEL="local.granola-sync"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$TEMPLATE" ]; then
  echo "Template not found: $TEMPLATE" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

# Render template (escape sed delimiters in case paths contain unusual chars).
sed -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" "$TEMPLATE" > "$TARGET"

# Bootout if already loaded, then bootstrap fresh.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"

echo "Installed: $TARGET"
echo "Verify:    launchctl print gui/\$(id -u)/$LABEL | grep -E 'state|run count|last exit'"
echo "Test fire: launchctl kickstart -k gui/\$(id -u)/$LABEL"
echo "Uninstall: launchctl bootout gui/\$(id -u)/$LABEL && rm '$TARGET'"
