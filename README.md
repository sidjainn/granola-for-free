# free-granola

Pull your Granola meeting notes into a local Obsidian vault as plain markdown,
with a folder-approval step so nothing lands in the wrong place.

## What it does

Twice a week (Wed + Sat), it sweeps the last 20 days of Granola meetings, works
out which ones are missing from your vault, proposes a folder for each, and
shows you a table. Nothing is written until you approve. After approval it
renders the notes, commits, and pushes.

The vault is also registered as a Google Drive mirrored root, so notes land in
two places: the git remote and Drive.

## What you get per note

```markdown
---
title: "weekly check-ins ek ai"
date: 2026-07-20
start: 2026-07-20T16:00:00+05:30
attendees:
  - "[[sidjainn@gmail.com]]"
granola_id: "72b37dcc-..."
folder: "ek-ai"
tags: [ek-ai, granola]
---

# weekly check-ins ek ai

## Notes          <- your own private notes, when the meeting had any
## AI Summary     <- Granola's generated summary
```

## Known ceiling (free Granola tier)

The MCP connector gates three things behind paid tiers. These are hard limits,
not bugs:

| Field | Available? |
|---|---|
| Title, date, attendees | yes |
| Private notes, AI summary | yes |
| **Transcript** | **no** — paid tiers only |
| **Granola folder metadata** | **no** — paid tiers only |
| **Meeting end time** | **no** — not exposed |

Because folder metadata is unreadable, folder placement is a *proposal you
approve*, never Granola's real folder. That approval step is the whole point of
the review skill.

## Setup

No third-party dependencies — Python 3.11+ only (`tomllib` is stdlib). A venv is
optional; the skill uses `.venv/bin/python` if present and falls back to
`python3`.

Set `vault_path_glob` in `config.toml` to your vault folder.

You also need the **Granola connector** authorised in claude.ai connector
settings. Verify with `/granola-review-sync` — if `list_meetings` returns an
auth error, re-authorise it there.

## Usage

```
/granola-review-sync            # sweep last 20 days, approve folders, write, push
/granola-review-sync --days 45  # wider sweep
/granola-chat ek-ai* what action items are still open?
```

The scheduled run lives at `~/.claude/scheduled-tasks/granola-review-sync/`
(cron `7 9 * * 3,6`). It only fires while the Claude app is open; if the app is
closed at that time, it runs on next launch.

## Layout

```
scripts/
  config.py         # resolves vault_path from config.toml
  vault.py          # markdown rendering, slugs, atomic write
  mcp_backfill.py   # --index | --folders | stdin JSON -> notes
.claude/skills/
  granola-review-sync/SKILL.md
  granola-chat/SKILL.md
```

`mcp_backfill.py` never touches the sync state file and always skips a note whose
file already exists, so re-running it is safe.

## History

Until 2026-07-16 this read Granola's local desktop store directly. Granola then
moved credentials into an encrypted `granola.db` whose key is not recoverable
from disk, which broke that path permanently — downgrading the app does not help,
because the storage format is driven by server-side feature flags rather than the
client version. The whole desktop-store pipeline (`sync.py`, `granola_api.py`,
`granola_client.py`, `sync-daily.sh`, the `local.granola-sync` LaunchAgent) was
removed on 2026-08-13 and replaced by the MCP connector path described above.

The trade is transcripts for reliability: the connector cannot serve transcripts
on a free tier, but it also cannot be broken by Granola changing its local
encryption.

## Limitations

- **Read-only.** Does not push edits back to Granola.
- **30-day lookback cap.** `list_meetings` accepts at most `last_30_days`, so a
  gap longer than that needs a manual catch-up.
- **Approval required.** By design, the sync will not run fully unattended.

---

## Credits

Built by [@sidjainn](https://github.com/sidjainn) — [sidjainn.github.io](https://sidjainn.github.io).
