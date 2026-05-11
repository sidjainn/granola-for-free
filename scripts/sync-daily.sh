#!/bin/bash
# Daily Granola sync wrapper. Logs to ~/Library/Logs/granola-sync.log.
# After sync, optionally commits + pushes the vault to a git remote (if vault is a git repo).
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
  # NOTE: --prune omitted on purpose. Cache wipes (e.g. Granola sign-out) can
  # empty the cache; pruning then deletes the whole vault. Run prune manually
  # when you are sure the cache is healthy.
  "$REPO/.venv/bin/python" "$REPO/scripts/sync.py" --api-fill --quiet

  # Resolve vault path from config (single source of truth).
  VAULT="$("$REPO/.venv/bin/python" -c "import sys; sys.path.insert(0, '$REPO/scripts'); import config; print(config.load().vault_path)")"

  if [ -d "$VAULT/.git" ]; then
    echo "--- vault git push ---"
    GIT_OPTS=(--git-dir="$VAULT/.git" --work-tree="$VAULT")
    git "${GIT_OPTS[@]}" add -A
    if ! git "${GIT_OPTS[@]}" diff --cached --quiet; then
      git "${GIT_OPTS[@]}" -c user.email=granola-sync@local -c user.name="granola-sync" \
          commit -m "sync $(date -u '+%Y-%m-%dT%H:%M:%SZ')" --quiet
      git "${GIT_OPTS[@]}" push --quiet 2>&1 || echo "WARN: git push failed (non-fatal)"
    else
      echo "no vault changes to commit"
    fi
  fi

  echo "===== $(date -u '+%Y-%m-%dT%H:%M:%SZ') sync end ====="
} >> "$LOG" 2>&1
