"""asyncpg pool. Every query that touches user data filters by workspace_id (DAT-03)."""

import json
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None


async def _init(conn: asyncpg.Connection) -> None:
    for t in ("json", "jsonb"):
        await conn.set_type_codec(t, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def open_pool(url: str, statement_cache_size: int = 100) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            url, min_size=1, max_size=10, init=_init, statement_cache_size=statement_cache_size
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("database pool is not open")
    return _pool


def row(r: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(r) if r is not None else None


def rows(rs: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [dict(r) for r in rs]
