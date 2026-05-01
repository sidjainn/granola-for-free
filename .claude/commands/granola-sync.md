---
description: Pull new/updated meetings from Granola into the local Obsidian vault.
argument-hint: "[--dry-run] [--full] [--since YYYY-MM-DD] [--quiet]"
---

Run the sync script and report the result.

## What to do

1. Run this Bash command, forwarding any flags the user passed in `$ARGUMENTS`:

   ```bash
   { [ -x .venv/bin/python ] && PY=.venv/bin/python || PY=python3; } && $PY scripts/sync.py $ARGUMENTS
   ```

2. The final stdout line is a JSON summary like:
   ```json
   {"added": 3, "updated": 1, "unchanged": 42, "skipped_before_since": 0, "errors": [], "vault": "...", "dry_run": false, "since": "..."}
   ```

3. Summarize for the user in 1–3 short lines:
   - `added`/`updated`/`unchanged` counts and the vault path
   - On `--dry-run`, say so explicitly
   - If `errors` is non-empty, list the first 3 and stop with a non-zero outcome

4. Do not re-read the generated markdown files or attempt to "verify" them unless the user asks. The script's sha256-based skip already enforces idempotency.

## Setup precondition (only verify if the script errors)

If the script fails with `ImportError: granola_mcp` or `ModuleNotFoundError: No module named 'granola_mcp'`, tell the user to run:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install git+https://github.com/pedramamini/GranolaMCP
```

If it fails with `Missing config file` or `vault_path_glob ... matched 0 paths`, point them to `config.toml` in the repo root.
