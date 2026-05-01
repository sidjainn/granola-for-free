"""Config loader. Resolves vault path from a single ~/.../GranolaVault glob match."""

from __future__ import annotations

import glob
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.toml"


@dataclass
class Config:
    vault_path: Path
    granola_cache_path: Path | None
    attendee_aliases: dict[str, str] = field(default_factory=dict)


def _expand(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def _resolve_vault(glob_pattern: str) -> Path:
    expanded = _expand(glob_pattern)
    matches = glob.glob(expanded)
    if not matches:
        # Allow the parent (Drive root) to exist while the GranolaVault folder doesn't yet.
        # If exactly one parent matches, create the vault folder there.
        parent_pattern = os.path.dirname(expanded)
        leaf = os.path.basename(expanded)
        parents = glob.glob(parent_pattern)
        if len(parents) == 1:
            candidate = Path(parents[0]) / leaf
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        raise SystemExit(
            f"vault_path_glob '{glob_pattern}' matched 0 paths and parent "
            f"'{parent_pattern}' matched {len(parents)}. Edit config.toml."
        )
    if len(matches) > 1:
        raise SystemExit(
            f"vault_path_glob '{glob_pattern}' matched {len(matches)} paths: "
            f"{matches}. Narrow the pattern in config.toml."
        )
    return Path(matches[0])


def load(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    if not path.exists():
        raise SystemExit(f"Missing config file: {path}")
    data = tomllib.loads(path.read_text())
    vault = _resolve_vault(data.get("vault_path_glob", ""))
    cache = data.get("granola_cache_path")
    cache_path = Path(_expand(cache)) if cache else None
    aliases = data.get("attendee_aliases", {}) or {}
    return Config(vault_path=vault, granola_cache_path=cache_path, attendee_aliases=aliases)


if __name__ == "__main__":
    cfg = load()
    print(f"vault_path: {cfg.vault_path}", file=sys.stderr)
    print(f"granola_cache_path: {cfg.granola_cache_path or '(default)'}", file=sys.stderr)
