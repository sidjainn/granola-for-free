"""Granola API client.

Reads auth from Granola desktop's local credential store and talks to
api.granola.ai directly. Replaces cache-file parsing since Granola moved
to encrypted local storage (May 2026 builds).

Auth file lookup order:
  1. stored-accounts.json — May 2026 multi-account format
  2. supabase.json — legacy single-account format

Both files contain WorkOS-issued access + refresh tokens. We never write
them back to disk to avoid racing with the desktop app.
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
CLIENT_VERSION = "5.354.0"
USER_AGENT = f"Granola/{CLIENT_VERSION}"
REFRESH_LEEWAY_SEC = 120

GRANOLA_DIR = Path.home() / "Library/Application Support/Granola"
STORED_ACCOUNTS_PATH = GRANOLA_DIR / "stored-accounts.json"
SUPABASE_PATH = GRANOLA_DIR / "supabase.json"


class GranolaAPIError(RuntimeError):
    pass


def _b64url_json(seg: str) -> dict:
    pad = "=" * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg + pad))


def _jwt_exp(token: str) -> int:
    try:
        return int(_b64url_json(token.split(".")[1]).get("exp", 0))
    except Exception:
        return 0


def _read_stored_accounts() -> dict | None:
    if not STORED_ACCOUNTS_PATH.exists():
        return None
    raw = json.loads(STORED_ACCOUNTS_PATH.read_text())
    accounts = raw.get("accounts")
    if isinstance(accounts, str):
        accounts = json.loads(accounts)
    if not isinstance(accounts, list) or not accounts:
        return None
    acct = accounts[0]
    tok = acct.get("tokens")
    if isinstance(tok, str):
        tok = json.loads(tok)
    if not tok or "access_token" not in tok:
        return None
    return tok


def _read_legacy_supabase() -> dict | None:
    if not SUPABASE_PATH.exists():
        return None
    raw = json.loads(SUPABASE_PATH.read_text())
    tok = raw.get("workos_tokens") or raw.get("cognito_tokens")
    if isinstance(tok, str):
        tok = json.loads(tok)
    if not tok or "access_token" not in tok:
        return None
    return tok


def _read_tokens() -> dict:
    tok = _read_stored_accounts() or _read_legacy_supabase()
    if not tok:
        raise GranolaAPIError(
            f"No usable token in {STORED_ACCOUNTS_PATH} or {SUPABASE_PATH}. "
            "Open Granola desktop and sign in."
        )
    return tok


def _refresh(client_id: str, refresh_token: str) -> dict:
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
    tok = _read_tokens()
    access = tok["access_token"]
    exp = _jwt_exp(access)
    if exp == 0 or exp - time.time() > REFRESH_LEEWAY_SEC:
        return access
    payload = _b64url_json(access.split(".")[1])
    client_id = payload.get("client_id") or ""
    refresh = tok.get("refresh_token")
    if not client_id or not refresh:
        raise GranolaAPIError("missing client_id or refresh_token for token refresh")
    new = _refresh(client_id, refresh)
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
            "Accept": "*/*",
            "User-Agent": USER_AGENT,
            "X-Client-Version": CLIENT_VERSION,
        },
    )
    try:
        with request.urlopen(req, timeout=30) as r:
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

    def get_documents(
        self,
        limit: int = 100,
        offset: int = 0,
        include_panels: bool = True,
        include_last_viewed_panel: bool = True,
    ) -> dict:
        self._wait()
        return _post(
            "/v2/get-documents",
            {
                "limit": limit,
                "offset": offset,
                "include_last_viewed_panel": include_last_viewed_panel,
                "include_panels": include_panels,
            },
            self.token,
        )

    def iter_documents(self, page_size: int = 100, hard_cap: int = 10000) -> list[dict]:
        """Fetch every accessible document, paginating until exhaustion."""
        offset = 0
        out: list[dict] = []
        while len(out) < hard_cap:
            page = self.get_documents(limit=page_size, offset=offset)
            docs = page.get("docs") or []
            out.extend(docs)
            if len(docs) < page_size:
                break
            offset += page_size
        return out

    def get_document_lists(self, include_document_ids: bool = True) -> dict:
        self._wait()
        return _post(
            "/v1/get-document-lists-metadata",
            {
                "include_document_ids": include_document_ids,
                "include_only_joined_lists": False,
            },
            self.token,
        )

    def get_panels(self, document_id: str) -> list[dict]:
        self._wait()
        return _post("/v1/get-document-panels", {"document_id": document_id}, self.token)

    def get_transcript(self, document_id: str) -> list[dict]:
        self._wait()
        return _post("/v1/get-document-transcript", {"document_id": document_id}, self.token)
