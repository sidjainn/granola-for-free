"""API-backed meeting iterator. Replaces former cache-file parser.

Granola moved to encrypted local cache (cache-v6.json.enc) in May 2026.
The old plain cache-v6.json is no longer maintained by the desktop app,
so we pull the meeting list straight from api.granola.ai instead.

Exposes a Meeting facade with the attribute surface sync.py already
expects (id, title, start_time/end_time, participants, tags, summary,
human_notes, has_transcript, transcript.segments, folder_name, _raw).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from granola_api import GranolaAPI, GranolaAPIError


def _parse_iso(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Segment:
    speaker: str | None
    text: str


@dataclass
class Transcript:
    segments: list[Segment]


class Meeting:
    """Lightweight facade over the /v2/get-documents response shape."""

    def __init__(self, doc: dict, folder_name: str | None):
        self._raw = doc
        self.id: str = doc.get("id") or ""
        self.title: str = doc.get("title") or "Untitled"

        gce = doc.get("google_calendar_event") or {}
        start_str = (gce.get("start") or {}).get("dateTime") if gce else None
        end_str = (gce.get("end") or {}).get("dateTime") if gce else None
        self.start_time: datetime | None = _parse_iso(start_str) or _parse_iso(doc.get("created_at"))
        self.end_time: datetime | None = _parse_iso(end_str)

        people = doc.get("people") or {}
        attendees = people.get("attendees") or []
        cal_attendees = (gce.get("attendees") or []) if gce else []
        emails = []
        for src in (attendees, cal_attendees):
            for a in src:
                if isinstance(a, dict):
                    e = a.get("email") or a.get("Email")
                    if e and e not in emails:
                        emails.append(e)
        self.participants: list[str] = emails
        self.tags: list[str] = []
        self.summary: str | None = doc.get("summary") or doc.get("overview")
        self.human_notes: str | None = doc.get("notes_markdown") or doc.get("notes_plain")
        self.folder_name: str | None = folder_name

        self._transcript: Transcript | None = None
        self._transcript_loaded = False

    @property
    def transcript(self) -> Transcript | None:
        return self._transcript

    def has_transcript(self) -> bool:
        return self._transcript is not None and bool(self._transcript.segments)

    def set_transcript_segments(self, segs: list[tuple[str | None, str]]) -> None:
        self._transcript = Transcript([Segment(s, t) for s, t in segs])
        self._transcript_loaded = True


class APISession:
    """Holds the API client + folder map. Returned by open_parser()."""

    def __init__(self, api: GranolaAPI, folders: dict[str, str], docs: list[dict]):
        self.api = api
        self.folders = folders
        self.docs = docs


def open_parser(_cache_path=None) -> APISession:
    """Build an API-backed session.

    The cache_path argument is accepted for backwards compatibility with the
    prior pedramamini-based loader but is ignored — we no longer read the
    local cache file.
    """
    api = GranolaAPI()
    lists = api.get_document_lists(include_document_ids=True).get("lists") or {}
    folders: dict[str, str] = {}
    if isinstance(lists, dict):
        for lid, meta in lists.items():
            title = (meta or {}).get("title")
            if not title:
                continue
            for did in meta.get("document_ids") or []:
                folders[did] = title
    docs = api.iter_documents()
    return APISession(api=api, folders=folders, docs=docs)


def iter_meetings(session: APISession, include_trashed: bool = False) -> Iterator[Meeting]:
    for doc in session.docs:
        if not include_trashed:
            if doc.get("deleted_at") or doc.get("was_trashed"):
                continue
        m = Meeting(doc, session.folders.get(doc.get("id") or ""))
        yield m


__all__ = [
    "open_parser",
    "iter_meetings",
    "Meeting",
    "APISession",
    "Segment",
    "Transcript",
    "GranolaAPIError",
]
