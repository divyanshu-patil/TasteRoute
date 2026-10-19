"""Signed anonymous workspace tokens (SEC-04) and client IP hashing."""

import hashlib
import hmac
import uuid

from fastapi import Request

from .db import pool
from .errors import InvalidWorkspace
from .settings import get_settings


def _sig(workspace_id: str) -> str:
    key = get_settings().session_secret.get_secret_value().encode()
    return hmac.new(key, workspace_id.encode(), hashlib.sha256).hexdigest()


def sign(workspace_id: str) -> str:
    return f"{workspace_id}.{_sig(workspace_id)}"


def verify(token: str | None) -> str:
    if not token or "." not in token:
        raise InvalidWorkspace()
    ws, sig = token.rsplit(".", 1)
    try:
        uuid.UUID(ws)
    except ValueError as e:
        raise InvalidWorkspace() from e
    if not hmac.compare_digest(sig, _sig(ws)):
        raise InvalidWorkspace()
    return ws


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def ip_hash(request: Request) -> str:
    salt = get_settings().session_secret.get_secret_value()
    return hashlib.sha256(f"{salt}:{client_ip(request)}".encode()).hexdigest()[:32]


async def workspace_id(request: Request) -> str:
    """FastAPI dependency: header X-Workspace-Token, or ?token= for EventSource."""
    ws = verify(request.headers.get("x-workspace-token") or request.query_params.get("token"))
    found = await pool().fetchval(
        "update workspaces set last_seen_at = now() where id = $1 returning id", uuid.UUID(ws)
    )
    if not found:
        raise InvalidWorkspace()
    return ws
