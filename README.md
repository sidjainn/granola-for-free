# free-granola

Keep your Granola meeting notes forever, even on the free plan.

Granola's free plan hides notes older than 30 days. This tool pulls every meeting (notes, AI summary, transcript, folder, attendees) into a local Obsidian-compatible vault you own. Optionally syncs to Google Drive. Optionally backs up to a private GitHub repo. Runs daily on its own. You can also chat with the notes from Claude Code.

macOS only. Should work on Linux with small tweaks; Windows untested.

---

## What it does

- **Pulls** meetings from Granola's local desktop cache (`cache-v6.json`).
- **Enriches** with AI summaries + full transcripts via Granola's authenticated API (uses your already-signed-in desktop session token; no extra credentials).
- **Mirrors** Granola's folder structure under a vault directory.
- **Renders** each meeting as markdown with frontmatter (title, date, attendees, tags, granola_id).
- **Skips trashed** meetings; **prunes** vault when meetings are deleted.
- **Idempotent**: re-running rewrites only what actually changed.
- **Daily auto-sync** via launchd.
- **Optional git auto-push** to a private repo after each sync.
- **Chat** with the notes via a Claude Code slash command.

---

## Quick start

### 1. Prerequisites

- **Granola desktop** installed and signed in. Open it once so the cache populates.
- **Python 3.11+** (`python3 --version`).
- **Claude Code** for the `/granola-sync` and `/granola-chat` slash commands. Optional — scripts run standalone too.

### 2. Clone + install

```bash
git clone https://github.com/sidjainn/granola-for-free.git free-granola
cd free-granola
python3 -m venv .venv
source .venv/bin/activate
pip install git+https://github.com/pedramamini/GranolaMCP
```

### 3. Pick a vault location

Default: `~/GranolaVault` (regular home dir folder). Create it:

```bash
mkdir -p ~/GranolaVault
```

**Add Google Drive backup (recommended)**: install Google Drive for Desktop → sign in → Drive Preferences → **My Mac** tab → **Add folder** → pick `~/GranolaVault`. Drive mirrors it under `Computers > My Mac > GranolaVault` on the web.

> Why not put the vault directly inside `~/Library/CloudStorage/GoogleDrive-*/My Drive/`? macOS TCC blocks LaunchAgent (daily auto-sync) processes from accessing that mount. Computers mirror sidesteps this and works out of the box.

### 4. First sync

```bash
.venv/bin/python scripts/sync.py --full --api-fill --quiet
```

Pulls every meeting, fetches AI summaries + transcripts via API, writes the vault. ~30 seconds for ~100 meetings. Output is a JSON summary.

Open the vault in Obsidian: "Open folder as vault" → pick the folder.

### 5. Daily auto-sync (macOS)

Once-a-day pull at 09:00. Edit `scripts/granola-sync.plist.template` to change time.

```bash
./scripts/install-launchagent.sh
```

Verify:
```bash
launchctl print gui/$(id -u)/local.granola-sync | grep -E "state|run count|last exit"
```

Test fire (don't wait for 09:00):
```bash
launchctl kickstart -k gui/$(id -u)/local.granola-sync
tail -30 ~/Library/Logs/granola-sync.log
```

Uninstall:
```bash
launchctl bootout gui/$(id -u)/local.granola-sync
rm ~/Library/LaunchAgents/local.granola-sync.plist
```

### 6. Optional: GitHub backup

Adds a third backup layer. After each sync, vault gets `git add/commit/push`'d to a private repo.

1. Create a **private** repo on github.com/new (no README/license).
2. Init the vault as a git repo:
   ```bash
   cd "$(.venv/bin/python -c 'import sys; sys.path.insert(0,"scripts"); import config; print(config.load().vault_path)')"
   git init -b main
   git remote add origin https://github.com/<you>/<your-private-repo>.git
   git add -A
   git commit -m "initial vault snapshot"
   git push -u origin main
   ```

Daily wrapper auto-detects the `.git` dir and pushes after each sync. No further setup.

### 7. Chat with your notes

Inside Claude Code (with this repo open):

```
/granola-chat <folder-or-glob> <question>
```

Examples:
- `/granola-chat Personal what are recurring action items?`
- `/granola-chat "start-up*" what ideas keep coming up?`
- `/granola-chat * who have I been meeting with this week?`

First token = folder glob; rest = question. Folder names with spaces need quoting. Reads matching `.md` files (size-capped at ~200KB) and answers with file citations.

---

## Manual sync flags

```bash
.venv/bin/python scripts/sync.py [flags]
```

- `--full` — walk every meeting (default uses a 24h delta window after first run).
- `--api-fill` — fetch AI summaries + missing transcripts.
- `--prune` — delete vault files for meetings trashed in Granola.
- `--dry-run` — preview, write nothing.
- `--since YYYY-MM-DD` — only meetings on/after this date.
- `--quiet` — suppress per-meeting log lines.

---

## Vault layout

```
GranolaVault/
├── .granola-sync-state.json     # state; do not hand-edit
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
attendees: ["[[alex@example.com]]"]
granola_id: "abc123-..."
folder: "Personal"
tags: [granola, personal]
---

# 1:1 with Alex

## Notes
<your typed notes, if any>

## AI Summary
<Granola's AI-generated summary>

## Transcript
**microphone:** ...
**system:** ...
```

---

## How it works

1. **Cache read**: parses `~/Library/Application Support/Granola/cache-v6.json` → meetings with metadata.
2. **API enrich** (`--api-fill`): fetches `/v1/get-document-panels` and `/v1/get-document-transcript` from `api.granola.ai` using the WorkOS access token already stored in `~/Library/Application Support/Granola/supabase.json`. Token auto-refreshes via the stored refresh token.
3. **Render**: TipTap (ProseMirror) JSON → markdown.
4. **Write**: atomic per-file writes. State file tracks sha256 + cached API content.
5. **Prune**: trashed meetings + orphan vault files removed when `--prune` is set.

No data leaves your machine except calls to Granola's own API on your behalf.

---

## Troubleshooting

- **`externally-managed-environment` on `pip install`** → use the venv: `python3 -m venv .venv && source .venv/bin/activate`.
- **`vault_path_glob ... matched 0 paths`** → the vault directory doesn't exist. Create it or change the path in `config.toml`.
- **Cache version mismatch** → if Granola ships a new cache file (e.g. `cache-v7.json`), update `granola_cache_path` in `config.toml`.
- **`workos_tokens.access_token missing` warning** → Granola desktop signed out or token cleared. Open Granola, sign in. Sync still runs (cache-only) until then.
- **Daily sync didn't run** → check `~/Library/Logs/granola-sync.log` and `launchctl print gui/$(id -u)/local.granola-sync`.

---

## Limitations

- **Mac only** for the LaunchAgent. The Python sync runs anywhere with Python 3.11+.
- **Read-only**. Does not push edits back to Granola.
- **Schema fragility**. Granola's local cache and private API are undocumented; future Granola versions may break the parser.
- **TOS**. The API path uses your own session token to read your own data. Personal use only; don't redistribute.

---

## Credits

Built by [@sidjainn](https://github.com/sidjainn) — [sidjainn.github.io](https://sidjainn.github.io).
