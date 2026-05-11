"""free-granola sync entrypoint.

Reads meetings from the local Granola desktop cache via GranolaParser, renders
each as Obsidian-compatible markdown, and writes into the configured vault
folder. Idempotent: skips writes whose sha256 is unchanged.

Usage:
    python3 scripts/sync.py [--dry-run] [--full] [--since YYYY-MM-DD] [--quiet]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import config as cfg_mod
import vault as v
from state import State


def parse_since(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Accept date or full ISO.
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise SystemExit(f"--since: invalid datetime '{s}' ({e})")


def transcript_segments(meeting) -> list[tuple[str | None, str]]:
    if not meeting.has_transcript():
        return []
    t = meeting.transcript
    if not t:
        return []
    return [(seg.speaker, seg.text) for seg in t.segments if (seg.text or "").strip()]


def normalize_id(meeting) -> str:
    mid = meeting.id or ""
    if mid:
        return mid
    # Fallback: synthesize from title + start to keep state stable.
    title = (meeting.title or "untitled").strip()
    start = meeting.start_time.isoformat() if meeting.start_time else "no-start"
    return f"synth:{title}|{start}"


def plan_path(meeting, vault_root: Path, taken: dict[Path, str]) -> Path:
    folder_rel = v.folder_to_relpath(meeting.folder_name)
    granola_id = normalize_id(meeting)
    base_dir = vault_root / folder_rel
    name = v.filename_for(meeting.start_time, meeting.title, granola_id, collision=False)
    candidate = base_dir / name
    # Collision: same path, different meeting → append id suffix.
    existing = taken.get(candidate)
    if existing is not None and existing != granola_id:
        name = v.filename_for(meeting.start_time, meeting.title, granola_id, collision=True)
        candidate = base_dir / name
    taken[candidate] = granola_id
    return candidate


def main() -> int:
    ap = argparse.ArgumentParser(prog="granola-sync")
    ap.add_argument("--dry-run", action="store_true", help="Print plan, write nothing.")
    ap.add_argument("--full", action="store_true", help="Ignore last_sync_iso; rewalk everything.")
    ap.add_argument("--since", help="ISO date or datetime; only meetings starting at or after.")
    ap.add_argument("--quiet", action="store_true", help="Suppress per-meeting log lines.")
    ap.add_argument("--prune", action="store_true", help="Delete vault files for meetings no longer in Granola cache.")
    ap.add_argument("--api-fill", action="store_true", help="Fetch missing notes (AI panels) and transcripts from Granola API.")
    args = ap.parse_args()

    cfg = cfg_mod.load()
    state = State.load(cfg.vault_path)

    import granola_client  # deferred so --help works without the dep installed

    parser = granola_client.open_parser(cfg.granola_cache_path)

    since: datetime | None = parse_since(args.since)
    if not since and not args.full and state.last_sync_iso:
        # 24h overlap window for safety.
        try:
            from datetime import timedelta

            last = datetime.fromisoformat(state.last_sync_iso.replace("Z", "+00:00"))
            since = last.astimezone(timezone.utc) - timedelta(hours=24)
        except ValueError:
            since = None

    counts = defaultdict(int)
    errors: list[dict] = []
    folder_seen: dict[str, str] = {}
    taken: dict[Path, str] = {}
    seen_ids: set[str] = set()

    api = None
    api_skipped_reason: str | None = None
    if args.api_fill:
        from granola_api import GranolaAPI, GranolaAPIError

        try:
            api = GranolaAPI()
        except GranolaAPIError as e:
            api_skipped_reason = str(e)
            print(
                f"warning: --api-fill disabled this run ({e}). "
                "Continuing with cache-only sync. Open Granola desktop and sign in to restore.",
                file=sys.stderr,
            )

    # Pre-populate `taken` from existing state to honor prior collision suffixes.
    for mid, entry in state.meetings.items():
        existing_path = entry.get("path")
        if existing_path:
            taken[cfg.vault_path / existing_path] = mid

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    for meeting in granola_client.iter_meetings(parser):
        try:
            granola_id = normalize_id(meeting)
            seen_ids.add(granola_id)
            start = meeting.start_time
            if since and start and start.astimezone(timezone.utc) < since.astimezone(timezone.utc):
                counts["skipped_before_since"] += 1
                continue

            folder_rel = v.folder_to_relpath(meeting.folder_name)
            if meeting.folder_name:
                folder_seen[meeting.folder_name] = folder_rel

            attendees = meeting.participants or []
            tags = meeting.tags or []
            summary = meeting.summary
            notes = meeting.human_notes
            segs = transcript_segments(meeting)
            raw_doc = getattr(meeting, "_raw", {}) or {}
            ydoc_ver = raw_doc.get("ydoc_version")

            prior_api = (state.meetings.get(granola_id) or {}).get("api") or {}
            cache_fresh = (
                "panels_md" in prior_api
                and prior_api.get("ydoc_version") == ydoc_ver
            )
            api_dirty = False
            ai_panels_md = prior_api.get("panels_md")

            # AI panels: fetch always when --api-fill and cache stale, regardless of local notes.
            if api is not None and not cache_fresh:
                from granola_api import GranolaAPIError
                from tiptap_md import render as tiptap_render

                try:
                    panels = api.get_panels(granola_id)
                    blocks = []
                    for p in sorted(panels or [], key=lambda x: x.get("created_at") or ""):
                        if p.get("deleted_at"):
                            continue
                        md = tiptap_render(p.get("content") or {})
                        if md.strip():
                            blocks.append(f"### {p.get('title') or 'Panel'}\n\n{md}")
                    ai_panels_md = "\n\n".join(blocks) or None
                    prior_api["panels_md"] = ai_panels_md
                    api_dirty = True
                    counts["api_notes_fetched"] += 1
                except GranolaAPIError as e:
                    errors.append({"id": granola_id, "stage": "panels", "error": str(e)})

            # Transcript: only fetch when local empty AND no cached segs.
            if not segs:
                if prior_api.get("transcript_segs"):
                    segs = [tuple(x) for x in prior_api["transcript_segs"]]
                elif api is not None:
                    from granola_api import GranolaAPIError

                    try:
                        tr = api.get_transcript(granola_id) or []
                        segs = [
                            ((s.get("source") or "Unknown"), (s.get("text") or "").strip())
                            for s in tr if (s.get("text") or "").strip()
                        ]
                        if segs:
                            prior_api["transcript_segs"] = segs
                            api_dirty = True
                        counts["api_transcripts_fetched"] += 1
                    except GranolaAPIError as e:
                        errors.append({"id": granola_id, "stage": "transcript", "error": str(e)})

            if api_dirty:
                prior_api["ydoc_version"] = ydoc_ver
                state.meetings.setdefault(granola_id, {})["api"] = prior_api

            content = v.render_markdown(
                title=meeting.title,
                start=meeting.start_time,
                end=meeting.end_time,
                attendees=attendees,
                granola_id=granola_id,
                folder_name=meeting.folder_name,
                tags=tags,
                summary=summary,
                notes=notes,
                transcript_segments=segs,
                aliases=cfg.attendee_aliases,
                ai_panels_md=ai_panels_md,
            )
            sha = v.sha256_text(content)

            prior = state.meetings.get(granola_id)
            target = plan_path(meeting, cfg.vault_path, taken)
            target_rel = target.relative_to(cfg.vault_path).as_posix()

            if prior and prior.get("sha256") == sha and (cfg.vault_path / prior.get("path", "")).exists():
                counts["unchanged"] += 1
                continue

            if args.dry_run:
                action = "update" if prior else "add"
                log(f"[dry-run] {action}: {target_rel}")
                counts[action] += 1
                continue

            v.atomic_write(target, content)
            action = "updated" if prior else "added"
            log(f"{action}: {target_rel}")
            counts[action] += 1

            existing_api = (state.meetings.get(granola_id) or {}).get("api")
            new_entry = {
                "sha256": sha,
                "path": target_rel,
                "folder_name": meeting.folder_name,
                "title": meeting.title,
                "start": meeting.start_time.isoformat() if meeting.start_time else None,
            }
            if existing_api is not None:
                new_entry["api"] = existing_api
            state.meetings[granola_id] = new_entry
        except Exception as e:
            errors.append(
                {
                    "id": getattr(meeting, "id", None),
                    "title": getattr(meeting, "title", None),
                    "error": f"{type(e).__name__}: {e}",
                }
            )
            if not args.quiet:
                traceback.print_exc()

    # Prune orphans: in state but not in current cache.
    pruned: list[str] = []
    prune_aborted_reason: str | None = None
    if args.prune:
        # Guardrail: if cache yields drastically fewer meetings than last known
        # state, abort instead of nuking the vault. Common cause: Granola
        # sign-out wipes the local cache to 0 docs.
        prior_count = len(state.meetings)
        if prior_count >= 10 and len(seen_ids) < prior_count * 0.5:
            prune_aborted_reason = (
                f"cache has {len(seen_ids)} meetings, state had {prior_count}. "
                "Refusing to prune — likely cache wipe (e.g. Granola sign-out). "
                "Sign in to Granola, let cache repopulate, then rerun with --prune."
            )
            print(f"WARN: prune aborted — {prune_aborted_reason}", file=sys.stderr)
        else:
            orphan_ids = [mid for mid in list(state.meetings.keys()) if mid not in seen_ids]
            for mid in orphan_ids:
                entry = state.meetings.get(mid, {})
                rel = entry.get("path")
                if rel:
                    fp = cfg.vault_path / rel
                    if args.dry_run:
                        log(f"[dry-run] delete: {rel}")
                    else:
                        try:
                            if fp.exists():
                                fp.unlink()
                            log(f"deleted: {rel}")
                        except OSError as e:
                            errors.append({"id": mid, "error": f"unlink {rel}: {e}"})
                            continue
                if not args.dry_run:
                    state.meetings.pop(mid, None)
                pruned.append(rel or mid)
                counts["deleted"] += 1

            # Disk-level orphan sweep: dated .md files not tracked in state.
            # Only deletes files matching YYYY-MM-DD-*.md to avoid touching user notes.
            dated_re = re.compile(r"^\d{4}-\d{2}-\d{2}-.+\.md$")
            tracked_paths = {e["path"] for e in state.meetings.values() if e.get("path")}
            # Also keep paths just written this run.
            tracked_paths.update(p.relative_to(cfg.vault_path).as_posix() for p in taken.keys())
            for f in cfg.vault_path.rglob("*.md"):
                rel = f.relative_to(cfg.vault_path).as_posix()
                if rel in tracked_paths:
                    continue
                if not dated_re.match(f.name):
                    continue
                if args.dry_run:
                    log(f"[dry-run] delete-orphan: {rel}")
                else:
                    try:
                        f.unlink()
                        log(f"deleted-orphan: {rel}")
                    except OSError as e:
                        errors.append({"path": rel, "error": f"unlink: {e}"})
                        continue
                pruned.append(rel)
                counts["deleted"] += 1

    # Refresh folders index.
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for folder_name, rel in folder_seen.items():
        state.folders[folder_name] = {"path": rel, "last_seen": now_iso}

    if not args.dry_run:
        state.stamp_now()
        state.save()

    summary = {
        "added": counts.get("added", 0) + counts.get("add", 0),
        "updated": counts.get("updated", 0) + counts.get("update", 0),
        "unchanged": counts.get("unchanged", 0),
        "deleted": counts.get("deleted", 0),
        "api_notes_fetched": counts.get("api_notes_fetched", 0),
        "api_transcripts_fetched": counts.get("api_transcripts_fetched", 0),
        "pruned_paths": pruned,
        "skipped_before_since": counts.get("skipped_before_since", 0),
        "errors": errors,
        "vault": str(cfg.vault_path),
        "dry_run": args.dry_run,
        "since": since.isoformat() if since else None,
        "api_fill_skipped": api_skipped_reason,
        "prune_aborted": prune_aborted_reason,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
