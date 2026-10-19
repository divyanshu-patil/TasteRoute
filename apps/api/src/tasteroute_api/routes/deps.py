import time
import uuid
from collections import defaultdict, deque
from typing import Any

from fastapi import Request

from ..agent.context import Services
from ..errors import AppError, NotFound, RateLimited
from ..security import client_ip


def svc(request: Request) -> Services:
    s: Services = request.app.state.svc
    return s


class Forbidden(AppError):
    code, status, title = "forbidden_workspace", 403, "This run is read-only"


class SlidingWindow:
    """In-process rate limit per key (one API instance, docs/16-runbook.md)."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_s: float) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            raise RateLimited()
        q.append(now)


limiter = SlidingWindow()


def rate(request: Request, bucket: str, limit: int, window_s: float) -> None:
    limiter.check(f"{bucket}:{client_ip(request)}", limit, window_s)


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
