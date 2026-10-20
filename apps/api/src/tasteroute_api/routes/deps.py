import time
import uuid
from collections import defaultdict, deque
from typing import Any

from fastapi import Request

from ..agent.context import Services
from ..errors import AppError, NotFound, QlooBudgetExceeded, RateLimited
from ..qloo.client import monthly_live_calls
from ..security import client_ip


def svc(request: Request) -> Services:
    s: Services = request.app.state.svc
    return s


class Forbidden(AppError):
    code, status, title = "forbidden_workspace", 403, "This run is read-only"


class SlidingWindow:
    """In-process rate limit per key (one API instance, docs/16-runbook.md). Keys idle for longer than their window are
    dropped every `prune_every` checks, so weeks of public traffic don't grow memory (REL-07)."""

    def __init__(self, prune_every: int = 1000) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.windows: dict[str, float] = {}
        self.prune_every = prune_every
        self.checks = 0

    def check(self, key: str, limit: int, window_s: float) -> None:
        now = time.monotonic()
        self.checks += 1
        if self.checks % self.prune_every == 0:
            self.prune(now)
        self.windows[key] = window_s
        q = self.hits[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            raise RateLimited()
        q.append(now)

    def prune(self, now: float) -> None:
        for k in [k for k, q in self.hits.items() if not q or q[-1] <= now - self.windows.get(k, 0)]:
            del self.hits[k]
            self.windows.pop(k, None)


limiter = SlidingWindow()


def rate(request: Request, bucket: str, limit: int, window_s: float) -> None:
    limiter.check(f"{bucket}:{client_ip(request)}", limit, window_s)


async def qloo_gate(s: Services) -> None:
    """The monthly Qloo budget gate, on every route that can make a live Qloo call (SEC-07)."""
    if s.qloo.configured and await monthly_live_calls(s.pool) >= 0.8 * s.settings.qloo_monthly_limit:
        raise QlooBudgetExceeded("The monthly Qloo budget is nearly used. Please explore the sample run instead.")


async def daily_capacity(s: Services) -> None:
    """Live runs by everyone in the last 24 h, demo runs excluded (SEC-06): one script can't spend the month's budget."""
    cap = s.settings.public_runs_per_day_global
    if cap > 0 and await s.pool.fetchval(
            "select count(*) from runs r join workspaces w on w.id = r.workspace_id "
            "where w.kind <> 'demo' and r.created_at > now() - interval '1 day'") >= cap:
        raise RateLimited("The public demo has used today's live runs. The sample run is always available.",
                          code="daily_capacity")


def as_uuid(v: str) -> uuid.UUID:
    try:
        return uuid.UUID(v)
    except (ValueError, TypeError) as e:
        raise NotFound() from e


async def get_run(s: Services, ws: str, run_id: str, *, write: bool = False) -> dict[str, Any]:
    """Own runs, or the demo workspace's runs read-only. Other workspaces' runs are 404 (DAT-03)."""
    r = await s.pool.fetchrow(
        "select r.*, w.kind as workspace_kind from runs r join workspaces w on w.id = r.workspace_id where r.id = $1",
        as_uuid(run_id),
    )
    if r is None:
        raise NotFound("Run not found")
    own = str(r["workspace_id"]) == ws
    if not own and r["workspace_kind"] != "demo":
        raise NotFound("Run not found")
    if write and not own:
        raise Forbidden("The sample run is read-only. Start your own run to change it.")
    return dict(r)
