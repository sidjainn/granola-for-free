"""Markdown rendering, slug generation, atomic write to vault."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable

INBOX_FOLDER = "Inbox"
SLUG_MAX_LEN = 60


def slugify(text: str | None) -> str:
    if not text:
        return "untitled"
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    norm = norm.lower()
    norm = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")
    if not norm:
        norm = "untitled"
    return norm[:SLUG_MAX_LEN].rstrip("-") or "untitled"


def folder_to_relpath(folder_name: str | None) -> str:
    """Granola folders are flat names; mirror them as single-level dirs."""
    if not folder_name:
        return INBOX_FOLDER
    cleaned = folder_name.strip()
    if not cleaned:
        return INBOX_FOLDER
    # Strip path separators to keep folder structure flat (Granola has no nesting).
    cleaned = cleaned.replace(os.sep, "-").replace("/", "-")
    return cleaned


def folder_to_tag(folder_name: str | None) -> str:
    base = folder_to_relpath(folder_name)
    return slugify(base)


def date_prefix(start: datetime | None) -> str:
    if not start:
        return "0000-00-00"
    return start.strftime("%Y-%m-%d")


def filename_for(start: datetime | None, title: str | None, granola_id: str, collision: bool) -> str:
    base = f"{date_prefix(start)}-{slugify(title)}"
    if collision:
        suffix = (granola_id or "")[:8] or "noid"
        base = f"{base}-{suffix}"
    return base + ".md"


def _yaml_str(s: str) -> str:
    """Minimal YAML string escaper. Quote and escape backslash + double-quote."""
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _yaml_list(items: Iterable[str]) -> list[str]:
    out = []
    for item in items:
        if item is None:
            continue
        out.append(f"  - {_yaml_str(str(item))}")
    return out


def render_markdown(
    *,
    title: str | None,
    start: datetime | None,
    end: datetime | None,
    attendees: list[str],
    granola_id: str,
    folder_name: str | None,
    tags: list[str],
    summary: str | None,
    notes: str | None,
    transcript_segments: list[tuple[str | None, str]],
    aliases: dict[str, str] | None = None,
    ai_panels_md: str | None = None,
) -> str:
    aliases = aliases or {}
    title_clean = (title or "Untitled meeting").strip()

    def alias(name: str) -> str:
        return aliases.get(name, name)

    attendee_links = [f"[[{alias(a)}]]" for a in attendees if a]

    folder_tag = folder_to_tag(folder_name)
    all_tags = sorted({"granola", folder_tag, *[slugify(t) for t in tags if t]})

    lines: list[str] = ["---"]
    lines.append(f"title: {_yaml_str(title_clean)}")
    if start:
        lines.append(f"date: {start.strftime('%Y-%m-%d')}")
        lines.append(f"start: {start.isoformat()}")
    if end:
        lines.append(f"end: {end.isoformat()}")
    if attendee_links:
        lines.append("attendees:")
        lines.extend(_yaml_list(attendee_links))
    else:
        lines.append("attendees: []")
    lines.append(f"granola_id: {_yaml_str(granola_id or '')}")
    lines.append(f"folder: {_yaml_str(folder_to_relpath(folder_name))}")
    lines.append(f"tags: [{', '.join(all_tags)}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title_clean}")
    lines.append("")

    if summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(summary.strip())
        lines.append("")

    if notes:
        lines.append("## Notes")
        lines.append("")
        lines.append(notes.strip())
        lines.append("")

    if ai_panels_md and ai_panels_md.strip():
        lines.append("## AI Summary")
        lines.append("")
        lines.append(ai_panels_md.strip())
        lines.append("")

    if transcript_segments:
        lines.append("## Transcript")
        lines.append("")
        for speaker, text in transcript_segments:
            if not text:
                continue
            spk = speaker.strip() if speaker else "Unknown"
            lines.append(f"**{spk}:** {text.strip()}")
            lines.append("")

    body = "\n".join(lines).rstrip() + "\n"
    return body


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sync-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
