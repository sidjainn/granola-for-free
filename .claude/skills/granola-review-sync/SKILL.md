---
name: granola-review-sync
description: Review-and-approve Granola sync via the MCP connector — proposes a folder per new meeting, writes only what you approve, then pushes the vault.
argument-hint: "[--days N] (default 20)"
---

Sync new Granola meetings into the Obsidian vault via the **Granola MCP connector**,
presenting a folder proposal table for approval before anything is written.

## Why this exists

Meetings come from the Granola MCP connector over the network; nothing here
reads Granola desktop's local files. See the README's History section for why
the local-store approach was abandoned.

**Known ceiling — state this to the user once per run, briefly:**
transcripts, Granola folder metadata, and meeting end-times are gated to paid
Granola tiers. Notes written here carry title, date, attendees, private notes,
and AI summary only. Folder placement is *your proposal plus the user's
approval*, never Granola's real folder — it cannot be read on a free tier.

## What to do

### 1. Index what already exists

```bash
{ [ -x .venv/bin/python ] && PY=.venv/bin/python || PY=python3; } && $PY scripts/mcp_backfill.py --index
{ [ -x .venv/bin/python ] && PY=.venv/bin/python || PY=python3; } && $PY scripts/mcp_backfill.py --folders
```

Keep the `ids` set and the `folders` list. Folders are the only valid
placement targets — do not invent new ones unless the user asks.

### 2. Fetch the sweep window

Load the Granola connector tools if they are not already available:
`ToolSearch` with query `granola meetings`. You need `list_meetings` and
`get_meetings`. **Never call `get_meeting_transcript` or `list_meeting_folders`** —
both hard-fail on a free tier.

Call `list_meetings` with `time_range: "last_30_days"` and involvement
`{captured_by_me: true, listed_as_participant: true}`, then filter client-side to
the last **20 days** (or `--days N` from `$ARGUMENTS`). The 20-day sweep is
deliberate: it is wider than the 3–4 day gap between runs so a missed or
late-edited meeting still gets caught.

### 3. Diff

Drop every meeting whose id is already in the `ids` set. If nothing remains,
report "vault already up to date, N meetings checked" and **stop** — no table,
no commit.

### 4. Pull details

`get_meetings` in batches of **at most 10 ids**. Take `title`, date/time,
`known_participants` (use the email addresses), `private_notes`, and `summary`.
Unescape XML entities (`&amp;` `&lt;` `&gt;` `&quot;` `&apos;`) and drop
markdown-escaping artifacts like `\~`.

### 5. Propose folders and get approval

Judge each meeting from its content and the vault's existing conventions —
look at how similar past meetings were filed. Default to `Inbox` when genuinely
unsure rather than forcing a match.

Present exactly this table, then stop and wait:

| # | Date | Meeting | Proposed folder | Why |
|---|------|---------|-----------------|-----|

Ask the user to reply "approve" or name corrections (e.g. "3 → Jobs, 5 → Inbox").
Apply any corrections and proceed. If they reject a row entirely, drop that
meeting from the payload. **Do not write anything before approval.**

### 6. Write

Build a JSON array and pipe it in:

```json
[{"id": "...", "title": "...", "start": "YYYY-MM-DD HH:MM", "folder": "...",
  "attendees": ["a@b.com"], "notes": "...or null", "ai_summary": "..."}]
```

```bash
{ [ -x .venv/bin/python ] && PY=.venv/bin/python || PY=python3; } && $PY scripts/mcp_backfill.py < payload.json
```

Write `payload.json` to a scratch path, not into the repo or the vault.
`start` is local IST wall-clock time; the script attaches `+05:30`.

### 7. Commit and push

Resolve the vault path from the script output, then:

```bash
git -C "$VAULT" add -A
git -C "$VAULT" -c user.email=granola-sync@local -c user.name="granola-sync" commit -q -F - <<'MSG'
mcp sync: <N> meetings <first date> - <last date>

Written via the Granola MCP connector (desktop-store sync unavailable).
Summary and private notes only; no transcripts. Folders approved by user.
MSG
git -C "$VAULT" push
```

Verify the push landed by comparing `git rev-parse main` against
`git ls-remote origin refs/heads/main` — do not rely on push output alone.

### 8. Report

Two or three lines: how many written, which folders, and the pushed commit sha.
Mention skipped/error counts only if non-zero.

## Notes

- The sync state file (`.granola-sync-state.json`) is intentionally left alone.
  Keeping these meetings out of state is what lets a restored desktop sync
  re-fetch them later with full transcripts.
- Filenames follow the standard convention, so a restored sync overwrites these
  in place rather than duplicating them.
- If `list_meetings` returns an auth error, the Granola connector needs
  re-authorising in claude.ai connector settings; say so and stop.
