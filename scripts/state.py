"""Sync state file: tracks per-meeting sha256 + path to enable idempotent re-syncs."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_FILENAME = ".granola-sync-state.json"
STATE_VERSION = 1


@dataclass
class State:
    path: Path
    version: int = STATE_VERSION
    last_sync_iso: str | None = None
    folders: dict[str, dict[str, Any]] = field(default_factory=dict)
    meetings: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, vault: Path) -> "State":
        p = vault / STATE_FILENAME
        if not p.exists():
            return cls(path=p)
        data = json.loads(p.read_text())
        return cls(
            path=p,
            version=data.get("version", STATE_VERSION),
            last_sync_iso=data.get("last_sync_iso"),
            folders=data.get("folders", {}) or {},
            meetings=data.get("meetings", {}) or {},
        )

    def save(self) -> None:
        payload = {
            "version": self.version,
            "last_sync_iso": self.last_sync_iso,
            "folders": self.folders,
            "meetings": self.meetings,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def stamp_now(self) -> None:
        self.last_sync_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
