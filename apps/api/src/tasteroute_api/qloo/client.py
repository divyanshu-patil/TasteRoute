"""Qloo HTTP client: rate limit, retries, cache (qloo_calls), per-run budget, trace, typed errors."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import asyncpg
import httpx

from ..errors import (
    QlooAuthError,
    QlooBadRequest,
    QlooBudgetExceeded,
    QlooError,
    QlooRateLimited,
    QlooUnconfigured,
)
from .compact import compact_response

Params = Sequence[tuple[str, str]]
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
RETRY_STATUS = {429, 502, 503, 504}
BACKOFF = (0.5, 1.0, 2.0)
MAX_RETRY_AFTER = 30.0


class TokenBucket:
    """Evenly spaced acquisitions at `rate` per second (capacity 1, so no bursts above the limit)."""

    def __init__(
        self,
        rate: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.rate = rate
        self.clock = clock
        self.sleep = sleep
        self.next_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self.clock()
            wait = self.next_at - now
            if wait > 0:
                await self.sleep(wait)
                now = self.next_at
            self.next_at = now + 1.0 / self.rate


@dataclass
class Trace:
    run_id: str | None = None
    step: str = "manual"
    emit: Emit | None = None


@dataclass
class QlooResult:
    body: dict[str, Any]
    call_id: str
    cache_hit: bool


def retry_after(value: str | None, cap: float = MAX_RETRY_AFTER) -> float:
    """Seconds from a Retry-After header (seconds or an HTTP date), capped (REL-06). 0 when absent or unreadable."""
    if not value:
        return 0.0
    try:
        secs = float(value)
    except ValueError:
        try:
            secs = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError):
            return 0.0
    return min(max(secs, 0.0), cap)


def cache_key(path: str, params: Params) -> str:
    norm = json.dumps(["GET", path, sorted((k, v) for k, v in params)])
    return hashlib.sha256(norm.encode()).hexdigest()


def result_count(body: dict[str, Any]) -> int:
    res = body.get("results")
    if isinstance(res, list):
        return len(res)
    if isinstance(res, dict):
        return len(res.get("entities") or res.get("tags") or [])
    return 0


class QlooClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        pool: asyncpg.Pool,
        rps: float = 4.0,
        timeout: float = 20.0,
        cache_ttl_hours: int = 72,
        max_calls_per_run: int = 120,
        http: httpx.AsyncClient | None = None,
        bucket: TokenBucket | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.api_key = api_key
        self.pool = pool
        self.ttl = timedelta(hours=cache_ttl_hours)
        self.max_calls_per_run = max_calls_per_run
        self.http = http or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self.bucket = bucket or TokenBucket(rps)
        self.sleep = sleep
        # Live calls started but not yet recorded, per run, so parallel calls can't overshoot the run cap (QLO-08).
        # ponytail: per-process lock; move the counter into Postgres if the API ever runs more than one instance
        self._inflight: dict[str, int] = {}
        self._budget_lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def get(self, path: str, params: Params, trace: Trace | None = None) -> QlooResult:
        trace = trace or Trace()
        if not self.api_key:
            raise QlooUnconfigured()
        key = cache_key(path, params)
        params_json = [list(p) for p in params]  # never contains the key: it travels in a header

        cached = await self.pool.fetchrow(
            "select id, response from qloo_calls where cache_key = $1 and cache_hit = false and status = 200 "
            "and response is not null and expires_at > now() order by created_at desc limit 1",
            key,
        )
        if cached:
            body = cached["response"]
            call_id = await self._record(trace, path, params_json, key, True, 200, 0, result_count(body), None, None)
            return QlooResult(body, call_id, True)

        run = trace.run_id
        if run:
            async with self._budget_lock:
                used = await self.pool.fetchval(
                    "select count(*) from qloo_calls where run_id = $1 and cache_hit = false", uuid.UUID(run)
                )
                if used + self._inflight.get(run, 0) >= self.max_calls_per_run:
                    raise QlooBudgetExceeded(f"This run reached its limit of {self.max_calls_per_run} live Qloo calls.")
                self._inflight[run] = self._inflight.get(run, 0) + 1
        try:
            status, body, ms = await self._fetch(path, params)
            if status != 200:
                await self._record(trace, path, params_json, key, False, status, ms, 0, None, None)
                raise self._error(status, body)
            compact = compact_response(body)
            call_id = await self._record(
                trace, path, params_json, key, False, 200, ms, result_count(compact), compact, datetime.now(UTC) + self.ttl
            )
        finally:
            if run:
                self._inflight[run] -= 1
                if not self._inflight[run]:
                    del self._inflight[run]
        return QlooResult(compact, call_id, False)

    async def _fetch(self, path: str, params: Params) -> tuple[int, Any, int]:
        last: tuple[int, Any, int] = (0, None, 0)
        for attempt, delay in enumerate(BACKOFF):
            await self.bucket.acquire()
            t = time.perf_counter()
            wait = delay + random.uniform(0, delay / 2)
            try:
                r = await self.http.get(path, params=list(params), headers={"X-Api-Key": self.api_key})
                ms = int((time.perf_counter() - t) * 1000)
                try:
                    body = r.json()
                except ValueError:
                    body = {"_raw": r.text[:500]}
                last = (r.status_code, body, ms)
                if r.status_code not in RETRY_STATUS:
                    return last
                wait = max(wait, retry_after(r.headers.get("retry-after")))
            except httpx.TimeoutException:
                last = (504, {"_raw": "timeout"}, int((time.perf_counter() - t) * 1000))
            except httpx.TransportError as e:
                last = (503, {"_raw": type(e).__name__}, int((time.perf_counter() - t) * 1000))
            if attempt < len(BACKOFF) - 1:
                await self.sleep(wait)
        return last

    @staticmethod
    def _error(status: int, body: Any) -> QlooError:
        msg = ""
        if isinstance(body, dict) and isinstance(body.get("errors"), list) and body["errors"]:
            msg = str(body["errors"][0].get("message", ""))[:300]
        if status == 401:
            return QlooAuthError()
        if status in (400, 403, 404, 422):
            return QlooBadRequest(msg or f"Qloo returned {status}")
        if status == 429:
            return QlooRateLimited()
        return QlooError(f"Qloo returned {status} after retries")

    async def _record(
        self,
        trace: Trace,
        path: str,
        params: list[list[str]],
        key: str,
        hit: bool,
        status: int,
        ms: int,
        count: int,
        response: Any,
        expires_at: datetime | None,
    ) -> str:
        call_id = await self.pool.fetchval(
            "insert into qloo_calls (run_id, step, endpoint, params, cache_key, cache_hit, status, duration_ms, "
            "result_count, response, expires_at) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) returning id",
            uuid.UUID(trace.run_id) if trace.run_id else None,
            trace.step,
            path,
            params,
            key,
            hit,
            status,
            ms,
            count,
            response,
            expires_at,
        )
        if trace.emit:
            await trace.emit(
                "qloo_call",
                {"call_id": str(call_id), "endpoint": path, "step": trace.step, "cache_hit": hit, "duration_ms": ms,
                 "status": status, "result_count": count},
            )
        return str(call_id)


async def stored_response(pool: asyncpg.Pool, call_id: str) -> Any:
    """Body behind a trace row; a cache-hit row points at the live row with the same key."""
    r = await pool.fetchrow("select cache_key, response from qloo_calls where id = $1", uuid.UUID(call_id))
    if r is None:
        return None
    if r["response"] is not None:
        return r["response"]
    return await pool.fetchval(
        "select response from qloo_calls where cache_key = $1 and response is not null order by created_at desc limit 1",
        r["cache_key"],
    )


async def monthly_live_calls(pool: asyncpg.Pool) -> int:
    return int(
        await pool.fetchval(
            "select count(*) from qloo_calls where cache_hit = false and created_at > now() - interval '30 days'"
        )
    )
