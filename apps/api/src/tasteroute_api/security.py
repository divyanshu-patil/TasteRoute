"""Signed anonymous workspace tokens (SEC-04) and client IP hashing."""

import hashlib
import hmac
import logging
import time
import uuid

from fastapi import Request

from .db import pool
from .errors import InvalidWorkspace
from .settings import get_settings

log = logging.getLogger("tasteroute.security")


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


EVENTS_TTL_S = 600


def sign_events(run_id: str, ttl: int = EVENTS_TTL_S) -> str:
    """A short-lived token for one run's SSE stream (SEC-10). EventSource can't send headers, so it travels in the URL
    and lands in access logs; unlike the workspace token it opens nothing else and expires in 10 minutes."""
    exp = int(time.time()) + ttl
    return f"{run_id}.{exp}.{_sig(f'events:{run_id}.{exp}')}"


def verify_events(token: str | None, run_id: str) -> None:
    try:
        rid, exp, sig = (token or "").split(".")
        expired = int(exp) < time.time()
    except ValueError as e:
        raise InvalidWorkspace("Invalid or expired event token") from e
    if rid != run_id or expired or not hmac.compare_digest(sig, _sig(f"events:{rid}.{exp}")):
        raise InvalidWorkspace("Invalid or expired event token")


def client_ip(request: Request) -> str:
    """The address our own proxy saw (SEC-05). The leftmost X-Forwarded-For entries are whatever the client sent, so only
    the entry `trusted_proxy_hops` from the right is trusted; with no trusted proxy, the socket's peer."""
    hops = get_settings().trusted_proxy_hops
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    # Shape only, IPs hashed: with LOG_LEVEL=debug and one spoofed request, shows how many entries the host appends
    # (docs/16-runbook.md). ponytail: remove once TRUSTED_PROXY_HOPS is confirmed on the host.
    log.debug("x-forwarded-for shape: %s", [hashlib.sha256(p.encode()).hexdigest()[:6] for p in fwd])
    if hops > 0 and len(fwd) >= hops:
        return fwd[-hops]
    return request.client.host if request.client else "unknown"


def ip_hash(request: Request) -> str:
    salt = get_settings().session_secret.get_secret_value()
    return hashlib.sha256(f"{salt}:{client_ip(request)}".encode()).hexdigest()[:32]


async def workspace_id(request: Request) -> str:
    """FastAPI dependency: header X-Workspace-Token (never a query parameter, so it stays out of access logs)."""
    ws = verify(request.headers.get("x-workspace-token"))
    found = await pool().fetchval(
        "update workspaces set last_seen_at = now() where id = $1 returning id", uuid.UUID(ws)
    )
    if not found:
        raise InvalidWorkspace()
    return ws
