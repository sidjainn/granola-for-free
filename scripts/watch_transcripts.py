"""Watch Granola cache for transcript-count changes.

Run while clicking Transcript tab on meetings in Granola desktop.
Prints a line every time the cache's transcript map grows or new IDs appear.

Usage:
    .venv/bin/python scripts/watch_transcripts.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import config as cfg_mod


def load_transcripts(cache_path: Path) -> dict:
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    inner = raw.get("cache", raw)
    if isinstance(inner, str):
        inner = json.loads(inner)
    state = inner.get("state", inner)
    return state.get("transcripts", {}) or {}


def load_titles(cache_path: Path) -> dict[str, str]:
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    inner = raw.get("cache", raw)
    if isinstance(inner, str):
        inner = json.loads(inner)
    state = inner.get("state", inner)
    docs = state.get("documents", {}) or {}
    out = {}
    for d in (docs.values() if isinstance(docs, dict) else docs):
        out[d.get("id")] = d.get("title") or "(untitled)"
    return out


def main() -> int:
    cfg = cfg_mod.load()
    cache_path = cfg.granola_cache_path
    if not cache_path.exists():
        print(f"cache not found: {cache_path}", file=sys.stderr)
        return 2

    last_mtime = 0.0
    last_ids: set[str] = set()
    print(f"watching {cache_path}", file=sys.stderr)
    print("click Transcript tab on a meeting in Granola desktop. Ctrl-C to stop.", file=sys.stderr)
    print("-" * 60, file=sys.stderr)

    try:
        while True:
            try:
                mtime = cache_path.stat().st_mtime
            except FileNotFoundError:
                time.sleep(1.0)
                continue
            if mtime != last_mtime:
                last_mtime = mtime
                try:
                    transcripts = load_transcripts(cache_path)
                    titles = load_titles(cache_path)
                except (json.JSONDecodeError, OSError):
                    time.sleep(0.5)
                    continue
                ids = set(transcripts.keys())
                added = ids - last_ids
                removed = last_ids - ids
                if added or removed or not last_ids:
                    ts = time.strftime("%H:%M:%S")
                    print(f"[{ts}] transcript count = {len(ids)}")
                    for tid in sorted(added):
                        title = titles.get(tid, "?")
                        seg_count = len(transcripts.get(tid) or [])
                        print(f"  + {tid[:8]}  segments={seg_count}  {title}")
                    for tid in sorted(removed):
                        print(f"  - {tid[:8]}  (gone)")
                last_ids = ids
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
