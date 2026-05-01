"""Granola API client.

Fetches AI panel content (notes_markdown equivalent) and full transcripts
that don't live in cache-v6.json. Auth via WorkOS access token from
supabase.json.
"""
from __future__ import annotations

import base64
import gzip
import json
import time
from pathlib import Path
from typing import Any
from urllib import error, request

API_BASE = "https://api.granola.ai"
AUTH_BASE = "https://auth.granola.ai"
USER_AGENT = "Granola/6.20.0 (Macintosh; Intel Mac OS X 14_0)"
REFRESH_LEEWAY_SEC = 120  # refresh if token expires within this window


class GranolaAPIError(RuntimeError):
    pass


SUPABASE_PATH = Path.home() / "Library/Application Support/Granola/supabase.json"


def _b64url_json(seg: str) -> dict:
    pad = "=" * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg + pad))


def _jwt_exp(token: str) -> int:
    try:
        return int(_b64url_json(token.split(".")[1]).get("exp", 0))
    except Exception:
        return 0


def _read_workos_tokens() -> dict:
    if not SUPABASE_PATH.exists():
        raise GranolaAPIError(f"supabase.json missing at {SUPABASE_PATH}")
    raw = json.loads(SUPABASE_PATH.read_text())
    tok = raw.get("workos_tokens")
    if isinstance(tok, str):
        tok = json.loads(tok)
    if not tok or "access_token" not in tok:
        raise GranolaAPIError("workos_tokens.access_token missing")
    return tok


def _refresh_workos(client_id: str, refresh_token: str) -> dict:
    body = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    req = request.Request(
        f"{AUTH_BASE}/user_management/authenticate",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except error.HTTPError as e:
        body_raw = e.read().decode("utf-8", errors="replace")[:300]
        raise GranolaAPIError(f"refresh failed HTTP {e.code}: {body_raw}")


def load_access_token() -> str:
    tok = _read_workos_tokens()
    access = tok["access_token"]
    exp = _jwt_exp(access)
    if exp == 0 or exp - time.time() > REFRESH_LEEWAY_SEC:
        return access
    # Stale or expiring — refresh in memory only (do not write back, avoid race with Granola desktop).
    payload = _b64url_json(access.split(".")[1])
    client_id = payload.get("client_id") or ""
    refresh = tok.get("refresh_token")
    if not client_id or not refresh:
        raise GranolaAPIError("missing client_id or refresh_token for token refresh")
    new = _refresh_workos(client_id, refresh)
    if "access_token" not in new:
        raise GranolaAPIError(f"refresh response missing access_token: {list(new.keys())}")
    return new["access_token"]


def _post(path: str, body: dict, token: str) -> Any:
    req = request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with request.urlopen(req, timeout=20) as r:
            data = r.read()
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            return json.loads(data)
    except error.HTTPError as e:
        body_raw = e.read().decode("utf-8", errors="replace")[:200]
        raise GranolaAPIError(f"{path} HTTP {e.code}: {body_raw}")


class GranolaAPI:
    def __init__(self, token: str | None = None, throttle_sec: float = 0.15):
        self.token = token or load_access_token()
        self.throttle = throttle_sec
        self._last_call = 0.0

    def _wait(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self.throttle:
            time.sleep(self.throttle - elapsed)
        self._last_call = time.time()

    def get_panels(self, document_id: str) -> list[dict]:
        self._wait()
        return _post("/v1/get-document-panels", {"document_id": document_id}, self.token)

    def get_transcript(self, document_id: str) -> list[dict]:
        self._wait()
        return _post("/v1/get-document-transcript", {"document_id": document_id}, self.token)
