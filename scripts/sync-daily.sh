#!/bin/bash
# Daily Granola sync wrapper. Logs to ~/Library/Logs/granola-sync.log.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$HOME/Library/Logs"
LOG="$LOG_DIR/granola-sync.log"

mkdir -p "$LOG_DIR"
cd "$REPO"

{
  echo "===== $(date -u '+%Y-%m-%dT%H:%M:%SZ') sync start ====="
  if [ ! -x "$REPO/.venv/bin/python" ]; then
    echo "ERROR: venv missing at $REPO/.venv. Recreate with: python3 -m venv .venv && .venv/bin/pip install git+https://github.com/pedramamini/GranolaMCP"
    exit 1
  fi
  "$REPO/.venv/bin/python" "$REPO/scripts/sync.py" --prune --api-fill --quiet
  echo "===== $(date -u '+%Y-%m-%dT%H:%M:%SZ') sync end ====="
} >> "$LOG" 2>&1
