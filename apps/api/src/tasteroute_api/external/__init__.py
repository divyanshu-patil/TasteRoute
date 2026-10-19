"""Non-Qloo services. All non-fatal: failures reduce contacts or details, never block ranking."""

import hashlib
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
Fetch = Callable[[], Awaitable[tuple[int, Any]]]


def cache_key(endpoint: str, params: Any) -> str:
    return hashlib.sha256(json.dumps([endpoint, params], sort_keys=True, default=str).encode()).hexdigest()


async def cached_call(
    pool: asyncpg.Pool,
    service: str,
    endpoint: str,
    params: dict[str, Any],
    ttl: timedelta,
    fetch: Fetch,
    *,
    run_id: str | None = None,
    emit: Emit | None = None,
    cache: bool = True,
) -> tuple[int, Any, str, bool]:
    """Serve from external_calls if fresh, else fetch and store. Returns (status, body, call_id, cache_hit).
    `params` must never contain secrets (keys travel in headers)."""
    key = cache_key(endpoint, params)
    rid = uuid.UUID(run_id) if run_id else None
    hit = None
    if cache:
        hit = await pool.fetchrow(
            "select response from external_calls where service = $1 and cache_key = $2 and cache_hit = false "
            "and status = 200 and expires_at > now() order by created_at desc limit 1",
            service, key,
        )
    if hit is not None:
        status, body, ms, is_hit = 200, hit["response"], 0, True
    else:
        t = time.perf_counter()
        status, body = await fetch()
        ms, is_hit = int((time.perf_counter() - t) * 1000), False
    call_id = await pool.fetchval(
        "insert into external_calls (run_id, service, endpoint, params, cache_key, cache_hit, status, duration_ms, "
        "response, expires_at) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) returning id",
        rid, service, endpoint, params, key, is_hit, status, ms,
        None if is_hit or status != 200 else body,
        None if is_hit else datetime.now(UTC) + ttl,
    )
    if emit:
        await emit("external_call", {"call_id": str(call_id), "service": service, "cache_hit": is_hit, "status": status})
    return status, body, str(call_id), is_hit
