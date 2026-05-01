"""Wrapper around granola_mcp's GranolaParser. Handles both v3 (cache=str) and v6 (cache=dict) formats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

try:
    from granola_mcp import GranolaParser
    from granola_mcp.core.meeting import Meeting
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "granola_mcp not installed. Activate venv and run:\n"
        "  pip install git+https://github.com/pedramamini/GranolaMCP\n"
        f"(import error: {e})"
    )


def open_parser(cache_path: Path | None = None) -> GranolaParser:
    parser = GranolaParser(str(cache_path)) if cache_path else GranolaParser()
    raw = Path(parser.cache_path).read_text(encoding="utf-8")
    outer = json.loads(raw)
    if not isinstance(outer, dict) or "cache" not in outer:
        raise SystemExit(f"Unexpected cache structure in {parser.cache_path}")
    inner = outer["cache"]
    if isinstance(inner, str):
        inner = json.loads(inner)
    if not isinstance(inner, dict):
        raise SystemExit("cache.cache must decode to a dict")
    parser._raw_data = raw
    parser._cache_data = inner
    return parser


def iter_meetings(parser: GranolaParser, include_trashed: bool = False) -> Iterator[Meeting]:
    for raw in parser.get_meetings():
        if not include_trashed and (raw.get("deleted_at") or raw.get("was_trashed")):
            continue
        m = Meeting(raw)
        m._raw = raw  # type: ignore[attr-defined]
        yield m


__all__ = ["open_parser", "iter_meetings", "Meeting", "GranolaParser"]
