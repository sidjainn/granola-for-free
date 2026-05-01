---
description: Chat with your Granola meeting notes, scoped to a folder or glob.
argument-hint: "<folder-glob> <question>"
---

Answer the user's question grounded strictly in their local Granola vault.

## Inputs

`$ARGUMENTS` is a single string. Parse it as: first whitespace-separated token is the **folder glob**, everything after it is the **question**.

If `$ARGUMENTS` is empty or has only one token, ask the user to supply both. Example: `/granola-chat Work/Eng* what action items are open on auth?`

## Steps

1. **Resolve the vault path.** Run:
   ```bash
   { [ -x .venv/bin/python ] && PY=.venv/bin/python || PY=python3; } && $PY -c "import sys; sys.path.insert(0, 'scripts'); import config; print(config.load().vault_path)"
   ```
   Treat stdout as `<VAULT>`.

2. **Resolve the folder glob.** From `<VAULT>`, expand the user's glob (e.g. `Work/Eng*`) using the Glob tool with pattern `<VAULT>/<glob>` (append `/` if no trailing slash). If 0 directories match:
   - Run `ls "<VAULT>"` and show the user the available top-level folders.
   - Ask them to refine.
   - Stop.

3. **Enumerate meeting files.** Use Glob to find `**/*.md` under each matched folder. Exclude any path containing `/.` (dotfiles/dotdirs) so the state file is skipped.

4. **Size check.** Run:
   ```bash
   wc -c <file1> <file2> ... | tail -1
   ```
   Sum total bytes. If `> 200000`:
   - Group files by their immediate parent folder, sum sizes per folder.
   - Show the user a table of folder → bytes, ask them to narrow the glob.
   - Stop.

5. **Read all matching files** with the Read tool (one call per file is fine; do not summarize while reading).

6. **Answer the question.** Ground every claim in the file contents. When you assert something, cite the source filename in brackets after the sentence: `[2026-04-12-1-1-with-alex.md]`. If the answer isn't supported by the notes, say "Not found in these notes" — do not extrapolate.

7. **End with a Sources section** listing every filename you actually used (one per line).

## Style

- Be concise. Bullet points over prose.
- Quote at most one short snippet per cited file.
- If the user's question is ambiguous, answer the most likely interpretation and note the alternative.
