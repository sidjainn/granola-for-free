"""Write vault notes from MCP-sourced meeting data (transcript-free).

The Granola MCP connector exposes title/date/attendees/private-notes/AI-summary
but gates transcripts and folder metadata behind paid tiers. This renders what
is available, through the same vault.render_markdown that sync.py uses, so the
output is byte-compatible with a normal sync.

Filenames follow the standard convention, so if the desktop-store sync is ever
restored it overwrites these in place and adds the transcript. The sync state
file is deliberately NOT updated here -- leaving these meetings absent from
state is what lets a restored sync re-fetch them in full.

Modes:
    --index          print JSON {"ids": [...]} of granola_ids already in vault
    --folders        print JSON {"folders": [...]} of existing vault folders
    (default)        read JSON array of meetings on stdin, write them

stdin schema (default mode):
    [{"id": str, "title": str, "start": "YYYY-MM-DD HH:MM", "folder": str,
      "attendees": [str], "notes": str|null, "ai_summary": str|null}]
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import vault  # noqa: E402

IST_OFFSET = "+05:30"
ID_RE = re.compile(r'^granola_id:\s*"([^"]+)"', re.MULTILINE)


def vault_path() -> Path:
    return Path(config.load().vault_path)


def existing_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for md in root.rglob("*.md"):
        try:
            head = md.read_text(errors="ignore")[:2000]
        except OSError:
            continue
        m = ID_RE.search(head)
        if m:
            ids.add(m.group(1))
    return ids


def existing_folders(root: Path) -> list[str]:
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )


def parse_start(s: str) -> datetime:
    return datetime.fromisoformat(f"{s}:00{IST_OFFSET}")


def write_meetings(root: Path, meetings: list[dict]) -> dict:
    written, skipped, errors = [], [], []
    for m in meetings:
        try:
            start = parse_start(m["start"])
            fname = vault.filename_for(start, m["title"], m["id"], collision=False)
            rel = vault.folder_to_relpath(m.get("folder"))
            path = root / rel / fname

            if path.exists():
                skipped.append(f"{rel}/{fname}")
                continue

            body = vault.render_markdown(
                title=m["title"],
                start=start,
                end=None,  # not exposed by the MCP surface; omit over fabricate
                attendees=m.get("attendees") or [],
                granola_id=m["id"],
                folder_name=m.get("folder"),
                tags=[],
                summary=None,
                notes=m.get("notes"),
                transcript_segments=[],
                ai_panels_md=m.get("ai_summary"),
            )
            vault.atomic_write(path, body)
            written.append(f"{rel}/{fname}")
        except Exception as e:  # keep going; report per-meeting failures
            errors.append(f"{m.get('id', '?')}: {type(e).__name__}: {e}")

    return {"written": written, "skipped": skipped, "errors": errors}


def main() -> int:
    root = vault_path()
    if not root.is_dir():
        print(json.dumps({"errors": [f"vault not found: {root}"]}))
        return 1

    if "--index" in sys.argv:
        print(json.dumps({"ids": sorted(existing_ids(root))}))
        return 0

    if "--folders" in sys.argv:
        print(json.dumps({"folders": existing_folders(root)}))
        return 0

    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"errors": ["no stdin payload"]}))
        return 1

    result = write_meetings(root, json.loads(raw))
    result["vault"] = str(root)
    print(json.dumps(result, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
