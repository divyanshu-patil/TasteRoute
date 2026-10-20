"""Phase A: the public demo survives until judging ends (SEC-05..SEC-10, QLO-08, REL-04..REL-07)."""

import asyncio
import time
import uuid

import httpx
import pytest

from tasteroute_api.errors import QlooBudgetExceeded
from tasteroute_api.external import website
from tasteroute_api.main import check_production
from tasteroute_api.qloo.client import Trace, retry_after
from tasteroute_api.routes.deps import SlidingWindow
from tasteroute_api.security import sign_events
from tasteroute_api.services import runs as run_service
from tasteroute_api.settings import Settings

from ..conftest import BROOKLYN, make_brand, new_workspace, scout


def _run_body(brand):
    return {"brand_id": brand["brand_id"], "product_ids": brand["product_ids"], "city": BROOKLYN, "venue_types": ["cafe"]}


async def test_spoofed_forwarded_for_does_not_change_the_client(client, ws, svc):
    """SEC-05: only the entry our proxy appended counts; a client can't pick a fresh IP per request."""
    svc.settings.trusted_proxy_hops = 1
    try:
        brand = await make_brand(client, ws, svc)
        svc.settings.public_runs_per_ip_per_day = 1
        r = await client.post("/v1/runs", headers={**ws, "X-Forwarded-For": "1.2.3.4, 9.9.9.9"}, json=_run_body(brand))
        assert r.status_code == 202
        await run_service.drain()
        other = await new_workspace(client)
        r = await client.post("/v1/runs", headers={**other, "X-Forwarded-For": "5.6.7.8, 9.9.9.9"},
                              json=_run_body(await make_brand(client, other, svc)))
        assert r.status_code == 429 and r.json()["code"] == "rate_limited"
        assert len(await svc.pool.fetch("select distinct client_ip_hash from runs")) == 1
    finally:
        svc.settings.trusted_proxy_hops = 0
        svc.settings.public_runs_per_ip_per_day = 50


async def test_global_daily_cap(client, ws, svc):
    """SEC-06: past the global cap, run 41 gets 429 daily_capacity; demo runs don't count."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    await svc.pool.execute(
        "insert into runs (workspace_id, brand_id, city, venue_types, scoring_version, settings) "
        "select workspace_id, brand_id, city, venue_types, scoring_version, settings from runs, generate_series(1, 39)")
    svc.settings.public_runs_per_ip_per_day = 0
    try:
        r = await client.post("/v1/runs", headers=ws, json=_run_body(brand))
        assert r.status_code == 429 and r.json()["code"] == "daily_capacity"
        assert "sample run is always available" in r.json()["detail"]
        await svc.pool.execute("update workspaces set kind = 'demo' where id = (select workspace_id from runs where id = $1)",
                               uuid.UUID(run_id))
        mine = await new_workspace(client)
        r = await client.post("/v1/runs", headers=mine, json=_run_body(await make_brand(client, mine, svc)))
        assert r.status_code == 202
        await run_service.drain()
    finally:
        svc.settings.public_runs_per_ip_per_day = 50


async def test_resolve_and_search_respect_the_monthly_budget(client, ws, svc, fake_qloo):
    """SEC-07: every Qloo-calling route is gated; no Qloo request goes out."""
    brand = await make_brand(client, ws, svc, resolve=False)
    svc.settings.qloo_monthly_limit = 0
    try:
        n = len(fake_qloo.requests)
        r = await client.post(f"/v1/brands/{brand['brand_id']}/resolve", headers=ws)
        assert r.status_code == 429 and r.json()["code"] == "qloo_budget_exceeded"
        r = await client.get("/v1/qloo/search", headers=ws, params={"q": "Blue Bottle"})
        assert r.status_code == 429 and r.json()["code"] == "qloo_budget_exceeded"
        assert len(fake_qloo.requests) == n
    finally:
        svc.settings.qloo_monthly_limit = 10_000


async def test_resolve_is_rate_limited_per_ip(client, ws, svc):
    """SEC-07: the per-IP limiter covers resolve."""
    brand = await make_brand(client, ws, svc, resolve=False)
    svc.llm.provider.script = []
    codes = [(await client.post(f"/v1/brands/{brand['brand_id']}/resolve", headers=ws)).status_code for _ in range(21)]
    assert codes[-1] == 429 and 429 not in codes[:20]


async def test_parallel_calls_never_exceed_the_run_cap(client, ws, svc, fake_qloo):
    """QLO-08: 10 parallel calls with a cap of 5 make at most 5 live calls."""
    run_id = await scout(client, ws, await make_brand(client, ws, svc))
    await svc.pool.execute("delete from qloo_calls where run_id = $1", uuid.UUID(run_id))
    svc.qloo.max_calls_per_run = 5

    async def one(i):
        try:
            await svc.qloo.get("/search", [("query", f"q{i}"), ("types", "urn:entity:brand"), ("take", "5")], Trace(run_id=run_id))
            return "ok"
        except QlooBudgetExceeded:
            return "capped"

    try:
        out = await asyncio.gather(*[one(i) for i in range(10)])
    finally:
        svc.qloo.max_calls_per_run = 120
    live = await svc.pool.fetchval("select count(*) from qloo_calls where run_id = $1 and not cache_hit", uuid.UUID(run_id))
    assert live == out.count("ok") == 5 and len([r for r in fake_qloo.requests if r.get("query", "").startswith("q")]) == 5


async def test_health_reports_qloo_from_the_latest_live_call(client, svc):
    """REL-04: configured until a call proves it; ok after a recent 200; auth_failed after a 401. No live call."""
    assert (await client.get("/health")).json()["qloo"] == "configured"
    q = ("insert into qloo_calls (step, endpoint, params, cache_key, cache_hit, status, duration_ms, result_count, created_at) "
         "values ('t', '/search', '[]'::jsonb, $1, false, $2, 1, 0, now() - make_interval(mins => $3))")
    await svc.pool.execute(q, "a", 200, 1)
    assert (await client.get("/health")).json()["qloo"] == "ok"
    await svc.pool.execute(q, "b", 401, 0)
    assert (await client.get("/health")).json()["qloo"] == "auth_failed"


async def test_startup_closes_interrupted_runs(client, ws, svc):
    """REL-05: a run left running by a restart is closed with a clear message; a fresh one is left alone."""
    brand = await make_brand(client, ws, svc)
    old = await scout(client, ws, brand)
    fresh = await scout(client, ws, brand)
    await svc.pool.execute("update runs set status = 'running', created_at = now() - interval '1 hour' where id = $1", uuid.UUID(old))
    await svc.pool.execute("update run_events set created_at = now() - interval '1 hour' where run_id = $1", uuid.UUID(old))
    await svc.pool.execute("update runs set status = 'outreach_running' where id = $1", uuid.UUID(fresh))
    assert await run_service.sweep_interrupted(svc) == 1
    r = (await client.get(f"/v1/runs/{old}", headers=ws)).json()
    assert r["status"] == "failed" and r["error_code"] == "interrupted" and "restarted" in r["error_message"]
    assert (await client.get(f"/v1/runs/{fresh}", headers=ws)).json()["status"] == "outreach_running"


def test_production_refuses_the_default_secret():
    """SEC-08."""
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        check_production(Settings(app_env="production", session_secret="change-me"))
    check_production(Settings(app_env="production", session_secret="a-long-random-value"))
    check_production(Settings(app_env="development", session_secret="change-me"))


async def test_qloo_429_honours_retry_after(svc, fake_qloo):
    """REL-06: Retry-After is waited out (capped at 30 s) before the next attempt."""
    waits = []

    async def sleep(s):
        waits.append(s)

    def with_header(request):
        r = fake_qloo(request)
        if r.status_code == 429:
            r.headers["Retry-After"] = "7"
        return r

    svc.qloo.sleep = sleep
    fake_qloo.fail_next = [429]
    await svc.qloo.http.aclose()
    svc.qloo.http = httpx.AsyncClient(base_url="https://hackathon.api.qloo.com", transport=httpx.MockTransport(with_header))
    await svc.qloo.get("/search", [("query", "nothing"), ("types", "urn:entity:brand"), ("take", "5")])
    assert waits and waits[0] >= 7
    assert retry_after("120") == 30 and retry_after("soon") == 0 and retry_after(None) == 0


def test_limiter_drops_idle_keys():
    """REL-07."""
    w = SlidingWindow(prune_every=3)
    w.check("a", 5, 0.01)
    w.check("b", 5, 0.01)
    time.sleep(0.02)
    w.check("c", 5, 60)
    assert set(w.hits) == {"c"}


async def test_sse_takes_only_a_short_lived_run_token(client, ws, svc):
    """SEC-10: the workspace token in the URL opens nothing; an events token works for its run only, until it expires."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    other = await scout(client, ws, brand)
    assert (await client.get(f"/v1/runs/{run_id}/events", params={"token": ws["X-Workspace-Token"]})).status_code == 401
    t = (await client.post(f"/v1/runs/{run_id}/events-token", headers=ws)).json()
    assert t["expires_in"] == 600
    assert (await client.get(f"/v1/runs/{other}/events", params={"token": t["token"]})).status_code == 401
    assert (await client.get(f"/v1/runs/{run_id}/events", params={"token": sign_events(run_id, ttl=-1)})).status_code == 401
    async with client.stream("GET", f"/v1/runs/{run_id}/events", params={"token": t["token"]}) as r:
        assert r.status_code == 200


async def test_fetcher_refuses_a_rebind_to_a_private_address():
    """SEC-09: the connection resolves again and refuses a host that now points at 127.0.0.1."""
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])

    async def flip(host):
        return next(answers)

    await website.check_url("https://rebind.test/", flip)  # first lookup: public
    with pytest.raises(website.UrlNotAllowed):
        await website.PinnedBackend(flip).connect_tcp("rebind.test", 443)  # second lookup: private


async def public(host):
    return ["93.184.216.34"]


async def test_slow_drip_server_is_cut_off_at_the_deadline():
    """SEC-09: one deadline for the whole fetch, however slowly bytes arrive."""

    class Drip(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.05)
                yield b"<p>x</p>"

    def slow(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html"}, stream=Drip())

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as http:
        t = time.monotonic()
        with pytest.raises(website.WebsiteUnreadable, match="too long"):
            await website.WebsiteReader(http, public, deadline=0.3).fetch("https://slow.test/")
        assert time.monotonic() - t < 2


async def test_robots_redirect_to_a_private_address_is_refused():
    """SEC-09: robots.txt follows the same per-hop checks as pages."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/robots.txt"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>ok</p>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        page = await website.WebsiteReader(http, public).fetch("https://site.test/")
    assert page.status == 200 and not any("127.0.0.1" in u for u in seen)
