"""Run lifecycle: scout (automatic) and outreach (user-triggered) phases as background tasks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Coroutine
from typing import Any

import asyncpg

from ..agent.context import RunContext, Services, emit_event
from ..agent.loop import run_phase
from ..errors import AppError, QlooUnconfigured

log = logging.getLogger("tasteroute.runs")
_tasks: set[asyncio.Task[Any]] = set()
_outreach: dict[str, asyncio.Task[Any]] = {}  # by run id, so a running outreach can be cancelled
CANCELLED = "Stopped at your request. Contacts and drafts found so far are kept."


def spawn(coro: Coroutine[Any, Any, Any], run_id: str | None = None) -> asyncio.Task[Any]:
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    if run_id:
        _outreach[run_id] = t
        t.add_done_callback(lambda _: _outreach.pop(run_id) if _outreach.get(run_id) is t else None)
    return t


async def cancel_outreach(svc: Services, run_id: str) -> None:
    """Stops the run's outreach mid-way (LLM and web calls included). Also frees a run left running by an API restart."""
    t = _outreach.get(run_id)
    if t:
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)  # it has stopped writing before the status changes
    await _fail(svc, run_id, "outreach", AppError(CANCELLED, code="cancelled"), "scouted")


async def drain() -> None:
    """Wait for background runs (tests and shutdown)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


async def counters(pool: asyncpg.Pool, run_id: uuid.UUID) -> dict[str, int]:
    r = await pool.fetchrow(
        "select (select count(*) from qloo_calls where run_id = $1 and not cache_hit) qloo_live, "
        "(select count(*) from qloo_calls where run_id = $1 and cache_hit) qloo_cached, "
        "(select count(*) from external_calls where run_id = $1 and service = 'hunter' and not cache_hit) hunter, "
        "(select count(*) from external_calls where run_id = $1 and service = 'overpass' and not cache_hit) overpass, "
        "(select count(*) from external_calls where run_id = $1 and service = 'website' and not cache_hit) website, "
        "(select count(*) from llm_calls where run_id = $1) llm",
        run_id,
    )
    return dict(r)


async def _fail(svc: Services, run_id: str, phase: str, e: AppError, status: str) -> None:
    rid = uuid.UUID(run_id)
    await svc.pool.execute(
        "update runs set status = $2, error_code = $3, error_message = $4, counters = $5, finished_at = now() where id = $1",
        rid, status, e.code, e.detail[:500], await counters(svc.pool, rid),
    )
    await emit_event(svc.pool, run_id, "failed", {"phase": phase, "code": e.code, "message": e.detail})


INTERRUPTED = "The server restarted during this run. Start it again; cached Qloo calls make it cheap."


async def sweep_interrupted(svc: Services) -> int:
    """On startup: runs with no activity for 15 minutes can't still be running (one instance), so they are closed
    (REL-05). A scout becomes `failed`; an interrupted outreach keeps its ranking, like any outreach failure."""
    rows = await svc.pool.fetch(
        "select id::text, status from runs r where status in ('queued','running','outreach_running') and "
        "coalesce((select max(e.created_at) from run_events e where e.run_id = r.id), r.created_at) "
        "< now() - interval '15 minutes'")
    for r in rows:
        outreach = r["status"] == "outreach_running"
        await _fail(svc, r["id"], "outreach" if outreach else "scout", AppError(INTERRUPTED, code="interrupted"),
                    "scouted" if outreach else "failed")
    return len(rows)


async def run_scout(svc: Services, run_id: str) -> None:
    rid = uuid.UUID(run_id)
    await svc.pool.execute("update runs set status = 'running', phase = 'scout', started_at = now() where id = $1", rid)
    try:
        if not svc.qloo.configured:  # kill switch (QLO-02): fail before any LLM or Qloo call
            raise QlooUnconfigured()
        ctx = await RunContext.load(svc, run_id)
        await ctx.emit("phase_started", {"phase": "scout", "orchestration": "agent", "provider": svc.llm.name})
        orch, reason, summary = await run_phase(ctx, "scout")
        await svc.pool.execute(
            "update runs set status = 'scouted', orchestration = $2, orchestration_reason = $3, counters = $4, "
            "finished_at = now() where id = $1",
            rid, orch, reason, await counters(svc.pool, rid),
        )
        await ctx.emit("phase_done", {"phase": "scout", "summary": summary, "orchestration": orch, "reason": reason})
    except AppError as e:
        await _fail(svc, run_id, "scout", e, "failed")
    except Exception as e:  # pragma: no cover - logged, surfaced as a generic failure
        log.exception("scout failed")
        await _fail(svc, run_id, "scout", AppError(f"Unexpected error ({type(e).__name__})", code="internal_error"), "failed")


async def run_outreach(svc: Services, run_id: str, venue_ids: list[str], drafts_only: bool = False) -> None:
    rid = uuid.UUID(run_id)
    await svc.pool.execute("update runs set status = 'outreach_running', phase = 'outreach' where id = $1", rid)
    reason: str | None
    try:
        ctx = await RunContext.load(svc, run_id)
        await ctx.emit("phase_started", {"phase": "outreach", "orchestration": "agent", "provider": svc.llm.name})
        if drafts_only:
            from ..services.drafts import draft_pitches

            await ctx.emit("tool_call", {"step": 1, "tool": "draft_pitches", "args_summary": {"venue_ids": f"{len(venue_ids)} ids"}})
            result = await draft_pitches(ctx, venue_ids)
            await ctx.emit("step_done", {"step": 1, "tool": "draft_pitches", "summary": result})
            orch, reason, summary = "deterministic_fallback", "drafts regenerated on request", f"Drafted {result.get('drafted', 0)}."
        else:
            orch, reason, summary = await run_phase(ctx, "outreach", venue_ids)
        await svc.pool.execute(
            "update runs set status = 'done', counters = $2, finished_at = now(), error_code = null, error_message = null "
            "where id = $1", rid, await counters(svc.pool, rid))
        await ctx.emit("phase_done", {"phase": "outreach", "summary": summary, "orchestration": orch, "reason": reason})
    except AppError as e:
        await _fail(svc, run_id, "outreach", e, "scouted")
    except Exception as e:  # pragma: no cover
        log.exception("outreach failed")
        await _fail(svc, run_id, "outreach", AppError(f"Unexpected error ({type(e).__name__})", code="internal_error"), "scouted")
