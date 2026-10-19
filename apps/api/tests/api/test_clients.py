"""Qloo client against the test DB: cache (QLO-06), retries (REL-01), typed errors, per-run budget; Hunter polling."""

import httpx
import pytest

from tasteroute_api.errors import QlooBadRequest, QlooBudgetExceeded, QlooRateLimited
from tasteroute_api.external import hunter
from tasteroute_api.qloo import api
from tasteroute_api.qloo.client import Trace, monthly_live_calls

PARAMS = [("query", "Blue Bottle Coffee"), ("types", "urn:entity:brand"), ("take", "5")]


async def test_cache_reuses_response_within_ttl(svc, fake_qloo):
    a = await svc.qloo.get("/search", PARAMS)
    b = await svc.qloo.get("/search", list(reversed(PARAMS)))
    assert not a.cache_hit and b.cache_hit and a.body == b.body
    assert len(fake_qloo.requests) == 1
    assert await monthly_live_calls(svc.pool) == 1


async def test_retries_then_succeeds(svc, fake_qloo):
    fake_qloo.fail_next = [429, 503]
    r = await svc.qloo.get("/search", PARAMS)
    assert r.body["results"] and len(fake_qloo.requests) == 3


async def test_rate_limit_storm_raises_typed_error(svc, fake_qloo):
    fake_qloo.fail_next = [429, 429, 429]
    with pytest.raises(QlooRateLimited):
        await svc.qloo.get("/search", PARAMS)
    fake_qloo.fail_next = [400]
    with pytest.raises(QlooBadRequest):
        await svc.qloo.get("/search", [("query", "x")])


async def test_per_run_budget(svc):
    """Live calls per run are capped; cached responses stay available."""
    ws = await svc.pool.fetchval("insert into workspaces default values returning id")
    brand = await svc.pool.fetchval(
        "insert into brands (workspace_id, name, category, profile) values ($1, 'b', 'unsupported', '{}') returning id", ws)
    run = await svc.pool.fetchval(
        "insert into runs (workspace_id, brand_id, city, venue_types, scoring_version) "
        "values ($1, $2, '{}', array['cafe'], 't') returning id", ws, brand)
    svc.qloo.max_calls_per_run = 1
    t = Trace(run_id=str(run))
    await api.search(svc.qloo, "Blue Bottle Coffee", ["urn:entity:brand"], t)
    with pytest.raises(QlooBudgetExceeded):
        await api.search(svc.qloo, "Campari", ["urn:entity:brand"], t)
    brands, _ = await api.search(svc.qloo, "Blue Bottle Coffee", ["urn:entity:brand"], t)
    assert brands
    svc.qloo.max_calls_per_run = 120


async def test_hunter_verify_polls_once_on_202(svc, net):
    replies = [httpx.Response(202), httpx.Response(200, json={"data": {"status": "valid"}})]
    net["hunter"].side_effect = lambda request: replies.pop(0)
    slept = []

    async def sleep(s):
        slept.append(s)

    status = await hunter.verify(svc.pool, svc.http, "k", "hi@cafe.test", run_id=None, emit=None, sleep=sleep)
    assert status == "valid" and slept == [3]


async def test_hunter_domain_search_parses_and_451(svc, net):
    body = {"data": {"emails": [{"value": "Owner@Cafe.test", "type": "personal", "confidence": 91, "position": "Owner",
                                 "verification": {"status": "valid"}, "sources": [{"uri": "https://cafe.test/about"}]}]}}
    net["hunter"].side_effect = lambda request: httpx.Response(200, json=body)
    found, _ = await hunter.domain_search(svc.pool, svc.http, "k", "cafe.test", run_id=None, emit=None)
    assert found[0].value == "owner@cafe.test" and hunter.is_role(found[0].position)
    net["hunter"].side_effect = lambda request: httpx.Response(451, json={})
    with pytest.raises(hunter.HunterClaimed):
        await hunter.domain_search(svc.pool, svc.http, "k", "claimed.test", run_id=None, emit=None)
