"""Safety-critical API behaviour: kill switch, scoping, tokens, validation, demo mode, limits, intake."""

import csv
import io
import json
import uuid

import httpx
from pydantic import SecretStr

from tasteroute_api.llm import LLMResult
from tasteroute_api.services import runs as run_service

from ..conftest import BRAND, BROOKLYN, make_brand, new_workspace, scout


async def _venues(client, ws, run_id):
    return (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"]


async def test_kill_switch_without_qloo_key(client, ws, svc):
    """QLO-02: no key -> scout fails with qloo_unconfigured before any LLM or Qloo call; nothing ranked."""
    brand = await make_brand(client, ws, svc, resolve=False)
    svc.qloo.api_key = ""
    run_id = await scout(client, ws, brand)
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "failed" and run["error_code"] == "qloo_unconfigured"
    assert await _venues(client, ws, run_id) == []
    assert await svc.pool.fetchval("select count(*) from llm_calls where run_id = $1", uuid.UUID(run_id)) == 0
    health = (await client.get("/health")).json()
    assert health["qloo"] == "unconfigured"


async def test_kill_switch_on_qloo_auth_error(client, ws, svc, fake_qloo):
    """QLO-02: a 401 mid-run fails the phase; no ranking or drafting call."""
    brand = await make_brand(client, ws, svc)
    fake_qloo.status_override = 401
    run_id = await scout(client, ws, brand)
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "failed" and run["error_code"] == "qloo_auth"
    assert await _venues(client, ws, run_id) == []
    n = await svc.pool.fetchval("select count(*) from llm_calls where run_id = $1 and purpose = 'pitch'", uuid.UUID(run_id))
    assert n == 0


async def test_other_workspace_gets_404(client, ws, svc):
    """DAT-03."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    other = await new_workspace(client)
    assert (await client.get(f"/v1/runs/{run_id}", headers=other)).status_code == 404
    assert (await client.get(f"/v1/runs/{run_id}/venues", headers=other)).status_code == 404
    assert (await client.get(f"/v1/brands/{brand['brand_id']}", headers=other)).status_code == 404
    r = await client.post("/v1/runs", headers=other, json={
        "brand_id": brand["brand_id"], "product_ids": brand["product_ids"], "city": BROOKLYN, "venue_types": ["cafe"]})
    assert r.status_code == 404
    assert (await client.get("/v1/runs/not-a-uuid", headers=ws)).status_code == 404


async def test_workspace_tokens_are_signed(client, ws):
    """SEC-04."""
    assert (await client.get("/v1/categories")).json()["code"] == "invalid_workspace"
    token = ws["X-Workspace-Token"]
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    r = await client.get("/v1/categories", headers={"X-Workspace-Token": tampered})
    assert r.status_code == 401 and r.json()["code"] == "invalid_workspace"
    forged = f"{uuid.uuid4()}.{token.split('.')[1]}"
    assert (await client.get("/v1/categories", headers={"X-Workspace-Token": forged})).status_code == 401
    ok = await client.get("/v1/categories", headers=ws)
    assert ok.status_code == 200 and [c["id"] for c in ok.json()] == ["food_drink"]  # CAT-03: fashion hidden
    again = await client.post("/v1/workspaces/session", json={"workspace_token": token})
    assert again.json()["workspace_token"] == token


async def test_invalid_input_returns_problem(client, ws, svc):
    """API-02."""
    brand = await make_brand(client, ws, svc, resolve=False)
    bad_city = {**BROOKLYN, "bbox": [41, -74, 40, -73]}
    r = await client.post("/v1/runs", headers=ws, json={
        "brand_id": brand["brand_id"], "product_ids": brand["product_ids"], "city": bad_city, "venue_types": ["cafe"]})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "validation_error"
    r = await client.post("/v1/runs", headers=ws, json={
        "brand_id": brand["brand_id"], "product_ids": brand["product_ids"], "city": BROOKLYN, "venue_types": ["casino"]})
    assert r.status_code == 422
    r = await client.post("/v1/brands", headers=ws, json={**BRAND, "products": []})
    assert r.status_code == 422


async def test_run_needs_a_resolved_entity(client, ws, svc):
    """ENT-05: products confirmed with no entities -> no_entities_resolved."""
    brand = await make_brand(client, ws, svc, resolve=False)
    for pid in brand["product_ids"]:
        r = await client.put(f"/v1/products/{pid}/entities", headers=ws, json={"entities": []})
        assert r.status_code == 200
    run_id = await scout(client, ws, brand)
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "failed" and run["error_code"] == "no_entities_resolved"


async def test_add_entity_from_qloo_search(client, ws, svc):
    """ENT-04: only ids present in a stored Qloo search response are accepted."""
    brand = await make_brand(client, ws, svc, resolve=False)
    found = (await client.get("/v1/qloo/search", headers=ws, params={"q": "Blue Bottle Coffee"})).json()
    bb = next(e for e in found if e["name"] == "Blue Bottle Coffee")
    pid = brand["product_ids"][0]
    r = await client.put(f"/v1/products/{pid}/entities", headers=ws,
                         json={"entities": [{"entity_id": bb["entity_id"], "source_call_id": bb["source_call_id"]}]})
    assert r.status_code == 200 and r.json()[0]["entity_id"] == bb["entity_id"]
    r = await client.put(f"/v1/products/{pid}/entities", headers=ws,
                         json={"entities": [{"entity_id": "MADE-UP-ID", "source_call_id": bb["source_call_id"]}]})
    assert r.status_code == 422


async def test_unsupported_business_needs_override(client, ws, svc):
    """INT-04, CAT-02."""
    body = {**BRAND, "profile": {**BRAND["profile"], "category": "unsupported", "prospects_are_consumer_facing": False}}
    b = (await client.post("/v1/brands", headers=ws, json=body)).json()
    r = await client.post("/v1/runs", headers=ws, json={
        "brand_id": b["brand_id"], "product_ids": b["product_ids"], "city": BROOKLYN, "venue_types": ["cafe"]})
    assert r.status_code == 422 and r.json()["code"] == "unsupported_business"
    b2 = (await client.post("/v1/brands", headers=ws, json={**body, "unsupported_override": True})).json()
    r = await client.post("/v1/runs", headers=ws, json={
        "brand_id": b2["brand_id"], "product_ids": b2["product_ids"], "city": BROOKLYN, "venue_types": ["cafe"]})
    assert r.status_code == 202
    await run_service.drain()


async def test_intake_paths(client, ws, svc):
    """INT-02, INT-03, SEC-02."""
    profile = {"brand_name": "Fieldnote", "one_liner": "Cold brew", "category": "food_drink", "prospects_are_consumer_facing": True,
               "price_tier": "premium", "style_words": ["small-batch"], "products": [{"name": "Cold Brew"}]}
    svc.llm.provider.script = [LLMResult(content="Here you go:\n```json\n" + json.dumps(profile) + "\n```")]
    r = await client.post("/v1/brands/intake", headers=ws, json={"website_url": "https://fieldnote-coffee.test/"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["source"] == "llm" and out["profile"]["products"][0]["name"] == "Cold Brew" and out["pages"]

    svc.llm.provider.script = [LLMResult(content="not json"), LLMResult(content="still not json")]
    r = await client.post("/v1/brands/intake", headers=ws,
                          json={"website_url": "https://broken-site.test/", "description": "We make cold brew in Brooklyn."})
    out = r.json()
    assert r.status_code == 200 and out["source"] == "empty" and out["notice"]

    r = await client.post("/v1/brands/intake", headers=ws, json={"website_url": "http://169.254.169.254/latest/meta-data"})
    assert r.status_code == 422 and r.json()["code"] == "url_not_allowed"
    r = await client.post("/v1/brands/intake", headers=ws, json={"website_url": "https://broken-site.test/"})
    assert r.status_code == 422 and r.json()["code"] == "website_unreadable"


async def test_live_runs_are_limited_per_day(client, ws, svc):
    """DMO-02."""
    brand = await make_brand(client, ws, svc)
    svc.settings.public_runs_per_ip_per_day = 1
    await scout(client, ws, brand)
    r = await client.post("/v1/runs", headers=ws, json={
        "brand_id": brand["brand_id"], "product_ids": brand["product_ids"], "city": BROOKLYN, "venue_types": ["cafe"]})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    svc.settings.public_runs_per_ip_per_day = 50


async def test_search_endpoints_are_rate_limited(client, ws):
    """SEC-03."""
    codes = [(await client.get("/v1/cities/search", headers=ws, params={"q": "Brooklyn"})).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


async def test_llm_cap_falls_back_and_keeps_results(client, ws, svc):
    """LLM-05, DMO-04: the per-run LLM cap stops the agent; the deterministic plan finishes the run."""
    brand = await make_brand(client, ws, svc)
    svc.settings.llm_max_calls_per_run = 2
    run_id = await scout(client, ws, brand)
    svc.settings.llm_max_calls_per_run = 80
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "scouted" and run["orchestration"] == "deterministic_fallback"
    assert "cap" in run["orchestration_reason"]
    assert await svc.pool.fetchval("select count(*) from llm_calls where run_id = $1", uuid.UUID(run_id)) <= 2
    assert len(await _venues(client, ws, run_id)) > 0


async def test_demo_run_is_read_only_and_masked(client, ws, svc):
    """DMO-01, DMO-05: the sample works with keys unset; emails are masked in JSON and CSV; writes are refused."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    top = [v["venue_id"] for v in (await _venues(client, ws, run_id))[:4]]
    await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": top})
    await run_service.drain()
    await svc.pool.execute("update workspaces set kind = 'demo' where id = (select workspace_id from runs where id = $1)",
                           uuid.UUID(run_id))
    svc.qloo.api_key = ""
    svc.settings.ollama_api_key = SecretStr("")
    visitor = await new_workspace(client)
    demo = (await client.get("/v1/demo")).json()
    assert demo == {"run_id": run_id, "available": True}
    run = (await client.get(f"/v1/runs/{run_id}", headers=visitor)).json()
    assert run["is_demo"] and run["status"] == "done"
    contacts = (await client.get(f"/v1/runs/{run_id}/contacts", headers=visitor)).json()
    emails = [c["email"] for x in contacts for c in x["contacts"]]
    assert emails and all("***@" in e for e in emails)
    drafts = (await client.get(f"/v1/runs/{run_id}/drafts", headers=visitor)).json()
    assert drafts and all("***@" in d["contact_email"] and d["mailto"] is None for d in drafts)
    detail = (await client.get(f"/v1/runs/{run_id}/venues/{top[0]}", headers=visitor)).json()
    assert all("***@" in c["email"] for c in detail["contacts"])
    rows = list(csv.DictReader(io.StringIO((await client.get(f"/v1/runs/{run_id}/export.csv", headers=visitor)).text)))
    assert all(not r["contact_email"] or "***@" in r["contact_email"] for r in rows)
    r = await client.post(f"/v1/runs/{run_id}/contacts", headers=visitor, json={"venue_ids": top})
    assert r.status_code == 403
    r = await client.post(f"/v1/runs/{run_id}/rescore", headers=visitor, json={"target": 0.5, "lift": 0.5})
    assert r.status_code == 403


async def test_health_reports_without_secrets(client, svc):
    r = await client.get("/health")
    body = r.json()
    assert r.status_code == 200 and body["db"] == "ok" and body["llm"]["provider"] == "fake"
    assert "test-key" not in r.text and "test-secret" not in r.text


async def test_hunter_claimed_domain_is_suppressed(client, ws, svc, net):
    """CON-04, CON-06: 451 adds the domain to suppression and stores nothing; calls stay under the cap."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    top = [v["venue_id"] for v in (await _venues(client, ws, run_id))[:5]]
    svc.settings.hunter_api_key = SecretStr("hunter-test")
    svc.settings.hunter_max_calls_per_run = 2
    net["hunter"].side_effect = lambda request: httpx.Response(451, json={"errors": [{"id": "claimed_email"}]})
    await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": top})
    await run_service.drain()
    svc.settings.hunter_api_key = SecretStr("")
    assert net["hunter"].call_count <= 2
    sup = (await client.get("/v1/suppressions", headers=ws)).json()
    assert sup and all(s["reason"] == "claimed_email" for s in sup)
    contacts = (await client.get(f"/v1/runs/{run_id}/contacts", headers=ws)).json()
    suppressed = {s["value"] for s in sup}
    assert all(c["email"].split("@")[1] not in suppressed for x in contacts for c in x["contacts"])
    assert any("hunter (limit reached)" in x["checked_sources"] for x in contacts)


async def test_failed_product_query_marks_only_that_product_unscored(client, ws, svc, fake_qloo):
    """FIT-03."""
    brand = await make_brand(client, ws, svc)
    la_colombe = "D012BBB3-EA3F-45E6-BA69-1710C0947A7D"
    fake_qloo.fail_if = lambda p: 400 if "filter.results.entities" in p and p["signal.interests.entities"] == la_colombe else None
    run_id = await scout(client, ws, brand)
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "scouted"
    assert any("House Espresso could not be scored" in w for w in run["warnings"])
    venues = await _venues(client, ws, run_id)
    assert venues and all(v["best_product"]["name"] == "Cold Brew Concentrate" for v in venues)
    assert {v["best_product"]["label"] for v in venues} == {"single_product"}


async def test_step_limit_hands_over_to_deterministic_plan(client, ws, svc):
    """AGT-02."""
    brand = await make_brand(client, ws, svc)
    svc.settings.llm_max_steps_per_phase = 2
    run_id = await scout(client, ws, brand)
    svc.settings.llm_max_steps_per_phase = 12
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "scouted" and run["orchestration"] == "deterministic_fallback"
    assert "step limit of 2" in run["orchestration_reason"]
    steps = await svc.pool.fetchval(
        "select count(*) from llm_calls where run_id = $1 and purpose = 'agent_step'", uuid.UUID(run_id))
    assert steps == 2


async def test_text_replies_twice_fall_back(client, ws, svc):
    """AGT-03: the model answers in prose twice -> deterministic plan, reason recorded."""
    brand = await make_brand(client, ws, svc)
    svc.llm.provider.script = [LLMResult(content="I will rank venues."), LLMResult(content="Ranking now.")]
    run_id = await scout(client, ws, brand)
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["orchestration"] == "deterministic_fallback" and "text instead of tool calls" in run["orchestration_reason"]
    assert len(await _venues(client, ws, run_id)) > 0


async def test_rls_enabled_without_policies(svc):
    """DAT-02."""
    rows = await svc.pool.fetch(
        "select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind = 'r'")
    assert rows and all(r["relrowsecurity"] for r in rows)
    assert await svc.pool.fetchval("select count(*) from pg_policies where schemaname = 'public'") == 0
