"""Everything a tool needs for one run, loaded once per phase."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

import asyncpg
import httpx

from ..categories import Pack, pack_for
from ..llm import LLM
from ..qloo.client import QlooClient, Trace
from ..settings import Settings

_seq_locks: dict[str, asyncio.Lock] = {}


async def emit_event(pool: asyncpg.Pool, run_id: str, type_: str, payload: dict[str, Any]) -> int:
    """Append a run event with the next per-run seq. Returns the event's global id (SSE id)."""
    lock = _seq_locks.setdefault(run_id, asyncio.Lock())
    async with lock:
        return int(
            await pool.fetchval(
                "insert into run_events (run_id, seq, type, payload) values ($1, "
                "coalesce((select max(seq) from run_events where run_id = $1), 0) + 1, $2, $3) returning id",
                uuid.UUID(run_id), type_, payload,
            )
        )


@dataclass
class Services:
    """Process-wide clients, created in the app lifespan (or by tests)."""

    settings: Settings
    pool: asyncpg.Pool
    qloo: QlooClient
    llm: LLM
    http: httpx.AsyncClient  # external services (OSM, Hunter, websites)


@dataclass
class RunContext:
    svc: Services
    run_id: str
    workspace_id: str
    brand: dict[str, Any]
    products: dict[str, dict[str, Any]]  # product_id -> {name, kind, notes, entities}
    city: dict[str, Any]
    venue_types: list[str]
    pack: Pack
    settings_json: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def pool(self) -> asyncpg.Pool:
        return self.svc.pool

    @property
    def rid(self) -> uuid.UUID:
        return uuid.UUID(self.run_id)

    async def emit(self, type_: str, payload: dict[str, Any]) -> None:
        await emit_event(self.pool, self.run_id, type_, payload)

    async def warn(self, code: str, message: str) -> None:
        self.warnings.append(message)
        await self.emit("warning", {"code": code, "message": message})

    def trace(self, step: str) -> Trace:
        return Trace(run_id=self.run_id, step=step, emit=self.emit)

    async def save_settings(self) -> None:
        await self.pool.execute("update runs set settings = $2 where id = $1", self.rid, self.settings_json)

    @classmethod
    async def load(cls, svc: Services, run_id: str) -> RunContext:
        pool = svc.pool
        run = await pool.fetchrow("select * from runs where id = $1", uuid.UUID(run_id))
        if run is None:
            raise LookupError(run_id)
        brand = await pool.fetchrow("select * from brands where id = $1", run["brand_id"])
        prods = await pool.fetch(
            "select p.* from products p join run_products rp on rp.product_id = p.id where rp.run_id = $1 order by p.position",
            run["id"],
        )
        return cls(
            svc=svc,
            run_id=run_id,
            workspace_id=str(run["workspace_id"]),
            brand=dict(brand),
            products={str(p["id"]): dict(p) for p in prods},
            city=run["city"],
            venue_types=list(run["venue_types"]),
            pack=pack_for(brand["category"]),
            settings_json=dict(run["settings"] or {}),
        )
