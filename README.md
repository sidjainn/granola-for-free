# free-granola

Keep your Granola meeting notes forever, even on the free plan.

Granola's free plan hides notes older than 30 days. This tool pulls every meeting (notes, AI summary, transcript, folder, attendees) into a local Obsidian-compatible vault you own. Optionally syncs to Google Drive. Optionally runs daily on its own. You can also chat with the notes from Claude Code.

Tested on macOS only. Should work on Linux with small tweaks; Windows untested.

---

## What it does

- **Pulls** meetings from Granola's local desktop cache (`cache-v6.json`).
- **Enriches** with AI summaries + full transcripts via Granola's authenticated API (uses your already-signed-in desktop session token; no extra credentials).
- **Mirrors** Granola's folder structure flat under a vault directory.
- **Renders** each meeting as markdown with frontmatter (title, date, attendees, tags, granola_id).
- **Skips trashed** meetings; **prunes** vault when meetings are deleted.
- **Idempotent**: re-running rewrites only what actually changed (sha256 of rendered content).
- **Daily auto-sync** via launchd (macOS LaunchAgent).
- **Chat** with the notes via a Claude Code slash command.

---

## Prerequisites

1. **Granola desktop** installed and signed in. Open it at least once so the cache populates.
2. **Python 3.11+** (`python3 --version`).
3. **Claude Code** if you want the `/granola-sync` and `/granola-chat` slash commands. Optional — the same scripts work standalone from a terminal.
4. **Google Drive for Desktop** *(optional)* — only if you want the vault on Drive.

---

## Install

```bash
git clone <this-repo> free-granola
cd free-granola

# Isolated venv (Homebrew Python is externally-managed; PEP 668)
python3 -m venv .venv
source .venv/bin/activate
pip install git+https://github.com/pedramamini/GranolaMCP

# Pick a vault path. Default is ~/GranolaVault. To use Drive instead, see "Sync to Google Drive" below.
python3 scripts/config.py   # prints the resolved vault path; errors if path doesn't exist yet
```

If `scripts/config.py` errors, edit `config.toml`:

```toml
# Local-only:
vault_path_glob = "~/GranolaVault"

# Or Google Drive (after Drive for Desktop is installed and mounted):
# vault_path_glob = "~/Library/CloudStorage/GoogleDrive-*/My Drive/GranolaVault"
```

The vault directory must exist. Create it: `mkdir -p ~/GranolaVault`.

---

## First sync

```bash
.venv/bin/python scripts/sync.py --full --api-fill --dry-run --quiet   # preview
.venv/bin/python scripts/sync.py --full --api-fill --quiet             # run
```

Flags:
- `--full` — walk every meeting (default uses a 24h delta window after the first run).
- `--api-fill` — fetch AI summaries + missing transcripts via Granola API. **Recommended on first run.**
- `--prune` — delete vault files for meetings trashed in Granola.
- `--dry-run` — print plan, write nothing.
- `--since YYYY-MM-DD` — only meetings on/after this date.
- `--quiet` — suppress per-meeting log lines.

Output is a single JSON summary with counts: `added / updated / unchanged / deleted / api_notes_fetched / api_transcripts_fetched / errors`.

---

## Daily auto-sync (macOS)

A LaunchAgent fires `scripts/sync-daily.sh` once a day. Default: 09:00 local time.

**Install:**
```bash
./scripts/install-launchagent.sh
```

The installer renders `scripts/granola-sync.plist.template` with your `$HOME` and the repo path, then bootstraps it under the label `local.granola-sync`. Re-running the installer reinstalls cleanly.

To change the schedule, edit `scripts/granola-sync.plist.template` (`Hour` / `Minute`) and re-run the installer.

**Verify:**
```bash
launchctl print gui/$(id -u)/local.granola-sync | grep -E "(state|run count|last exit)"
```

**Test fire (without waiting for 09:00):**
```bash
launchctl kickstart -k gui/$(id -u)/local.granola-sync
while pgrep -f sync-daily.sh > /dev/null; do sleep 1; done
tail -30 ~/Library/Logs/granola-sync.log
```

**Behavior:**
- Laptop awake at 09:00 → runs.
- Laptop asleep → fires on wake.
- Laptop off / logged out → fires next login.
- For "fires while laptop off" you'd add a `pmset` wake schedule — not included.

**Token expiry:** the API access token is short-lived (~3h). The sync script auto-refreshes using the refresh token from `supabase.json`. No manual action needed.

**Uninstall:**
```bash
launchctl bootout gui/$(id -u)/local.granola-sync
rm ~/Library/LaunchAgents/local.granola-sync.plist
```

---

## Sync to Google Drive

1. Install Google Drive for Desktop and sign in. Wait until `~/Library/CloudStorage/GoogleDrive-<email>/My Drive/` appears.
2. Move the vault and update config:
   ```bash
   GD=$(ls -d ~/Library/CloudStorage/GoogleDrive-*/My\ Drive 2>/dev/null | head -1)
   mv ~/GranolaVault "$GD/GranolaVault"
   ```
3. Edit `config.toml`:
   ```toml
   vault_path_glob = "~/Library/CloudStorage/GoogleDrive-*/My Drive/GranolaVault"
   ```

The state file (`.granola-sync-state.json`) moves with the directory. Sync stays idempotent.

---

## Chat with your notes

Inside Claude Code (with this repo open):

```
/granola-chat <folder-or-glob> <question>
```

Examples:
- `/granola-chat Jobs what roles am I interviewing for?`
- `/granola-chat "start-up*" what ideas keep recurring?`
- `/granola-chat * who have I been meeting with this week?`

The first whitespace-separated token is the folder glob; the rest is the question. Folder names with spaces need quoting. The command reads matching `.md` files (size-capped at ~200KB to prevent context blowup) and answers with file citations and a `Sources` section.

---

## Vault layout

```
GranolaVault/
├── .granola-sync-state.json     # idempotency state; do not hand-edit
├── Personal/
│   └── 2026-04-12-1-1-with-alex.md
├── Work/
│   └── 2026-04-28-eng-standup.md
└── Inbox/                       # meetings with no folder in Granola
    └── 2026-04-30-quick-sync.md
```

Each markdown file:

```markdown
---
title: "1:1 with Alex"
date: 2026-04-12
start: 2026-04-12T15:00:00-07:00
attendees:
  - "[[alex@example.com]]"
granola_id: "abc123-..."
folder: "Personal"
tags: [granola, personal]
---

# 1:1 with Alex

## Notes
<your typed notes, if any>

## AI Summary
<Granola's AI-generated summary, if any>

## Transcript
**microphone:** ...
**system:** ...
```

---

## How the data flows

1. **Cache read**: `granola_mcp` parses `~/Library/Application Support/Granola/cache-v6.json` → list of meetings with metadata, folders, attendees.
2. **API enrich** (when `--api-fill` is on): for each meeting, fetch `/v1/get-document-panels` and `/v1/get-document-transcript` from `api.granola.ai` using the WorkOS access token already stored in `~/Library/Application Support/Granola/supabase.json`.
3. **Render**: TipTap (ProseMirror) JSON → markdown via `scripts/tiptap_md.py`.
4. **Write**: atomic write per file. State (`.granola-sync-state.json`) tracks `{sha256, path, ydoc_version, cached api content}` per meeting.
5. **Prune** (when `--prune` is on): trashed meetings + orphaned vault files are deleted.

No data is sent anywhere except calls to Granola's own API on your behalf. No third-party services.

---

## Troubleshooting

- **`externally-managed-environment` on `pip install`** → use the venv: `python3 -m venv .venv && source .venv/bin/activate`.
- **`vault_path_glob ... matched 0 paths`** → the vault directory doesn't exist yet. Create it (`mkdir -p ~/GranolaVault`) or change the path in `config.toml`.
- **Cache version mismatch** → if Granola ships a new cache file (e.g. `cache-v7.json`), update `granola_cache_path_glob` in `config.toml`.
- **API 401 Unauthorized in the daily log** → access token expired and Granola desktop wasn't open to refresh it. Sync script's refresher should handle this; if it doesn't, open Granola desktop once to mint a fresh refresh token.
- **`/granola-chat` says "0 directories matched"** → check spelling, glob the folder name verbatim (`ls ~/GranolaVault/` shows the canonical names).

---

## Limitations

- **Mac only** for the LaunchAgent. The Python sync itself runs anywhere with Python 3.11+.
- **Read-only**. Does not push edits back to Granola. The vault is a one-way mirror.
- **Schema fragility**. Granola's local cache and private API are undocumented; future Granola versions may break the parser. Pin or fork the dep if this matters.
- **Granola TOS**. The API path uses your own session token to read your own data. Treat this as personal use; don't redistribute the API client.

---

## License

MIT.
