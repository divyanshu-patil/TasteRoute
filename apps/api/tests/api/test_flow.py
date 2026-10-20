"""Flow A end to end over fixtures: intake -> resolve -> scout (agent) -> contacts -> drafts -> approve -> export."""

import asyncio
import csv
import io
import json
import re
import uuid

import httpx
from pydantic import SecretStr

from tasteroute_api.errors import LLMUnavailable
from tasteroute_api.llm.base import LLMResult
from tasteroute_api.services import runs as run_service

from .. import conftest
from ..conftest import BRAND, BROOKLYN, SPECIALTY, make_brand, scout


async def test_resolve_uses_qloo_ids_only(client, ws, svc):
    """ENT-01, ENT-02: LLM gives names; stored ids come from Qloo /search responses."""
    brand = await make_brand(client, ws, svc)
    res = brand["resolution"]
    assert [r["status"] for r in res] == ["resolved", "resolved"]
    ids = {e["entity_id"] for r in res for e in r["entities"]}
    assert ids == set(SPECIALTY)
    assert all(e["role"] == "comparable" and e["source_call_id"] for r in res for e in r["entities"])


async def test_scout_run_end_to_end(client, ws, svc, fake_qloo):
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "scouted", run
    assert run["orchestration"] == "agent"

    page = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()
    venues = page["items"]
    assert 15 <= len(venues) <= 60  # RNK-06
    assert [v["rank"] for v in venues] == list(range(1, len(venues) + 1))
    for v in venues:  # EVD-01, FIT-01, RNK-04
        assert v["reason"] and v["evidence_count"] >= 1
        assert v["confidence"] in ("high", "medium", "low")
        assert v["best_product"]["label"] in ("clear", "close", "tie")
        assert abs(v["lift"] - (v["target_pct"] - v["baseline_pct"])) < 1e-3
    # Lift reorders: ranking is not the raw target order (RNK-02)
    by_target = sorted(venues, key=lambda v: -v["target_pct"])
    assert [v["venue_id"] for v in by_target] != [v["venue_id"] for v in venues]

    detail = (await client.get(f"/v1/runs/{run_id}/venues/{venues[0]['venue_id']}", headers=ws)).json()
    assert len(detail["product_fit"]) == 2  # FIT-01
    kinds = {e["type"] for e in detail["evidence"]}
    assert {"qloo_affinity", "qloo_venue_profile", "qloo_product_fit"} <= kinds
    assert all(e["source_kind"] == "inference" for e in detail["evidence"] if e["type"] == "inference")  # EVD-03
    pf = next(e for e in detail["evidence"] if e["type"] == "qloo_product_fit")  # FIT-04: from Qloo per-product calls
    assert pf["source_kind"] == "qloo" and len(pf["value"]["affinities"]) == 2
    assert all(f["affinity"] is not None for f in detail["product_fit"])
    music = [e for v in venues[:10] for e in (await client.get(f"/v1/runs/{run_id}/venues/{v['venue_id']}", headers=ws)
                                               ).json()["evidence"] if e["type"] == "qloo_cross_domain"]
    assert music and all(e["source_kind"] == "qloo" and e["source_call_id"] for e in music)  # EVD-06
    assert all(len(e["value"]["fans_like"]) == 5 and 0 <= e["value"]["pct"] <= 1 for e in music)
    assert any("music your brands' fans like" in v["reason"] for v in venues)

    trace = (await client.get(f"/v1/runs/{run_id}/trace", headers=ws)).json()
    qloo = [t for t in trace if t["kind"] == "qloo"]
    trace_ids = {t["id"] for t in trace}
    for e in detail["evidence"]:  # EVD-02
        if e["source_call_id"]:
            assert e["source_call_id"] in trace_ids
    steps = {t["step"] for t in qloo}
    assert {"rank_venues", "match_products", "attach_evidence"} <= steps  # QLO-03 (search ran in the wizard)
    rank_calls = [t for t in qloo if t["step"] == "rank_venues"]
    assert len(rank_calls) == 2  # RNK-01: one target and one baseline per venue type
    assert any(t["kind"] == "llm" and t["step"] == "agent_step" for t in trace)
    assert any(t["kind"] == "tool" and t["name"] == "rank_venues" for t in trace)
    assert "test-key" not in json.dumps(trace)  # AGT-05: no secret in the trace


async def test_agent_and_fallback_give_identical_scores_and_cache(client, ws, svc, fake_qloo):
    """AGT-03, AGT-06, LLM-02, DMO-03: provider failure -> deterministic plan, same scores, zero live Qloo calls."""
    brand = await make_brand(client, ws, svc)
    first = await scout(client, ws, brand)
    live_before = len(fake_qloo.requests)
    svc.llm.provider.script = [LLMUnavailable("down")]
    second = await scout(client, ws, brand)
    run2 = (await client.get(f"/v1/runs/{second}", headers=ws)).json()
    assert run2["orchestration"] == "deterministic_fallback"
    assert "LLM unavailable" in run2["orchestration_reason"]
    assert len(fake_qloo.requests) == live_before
    assert run2["counters"]["qloo_live"] == 0 and run2["counters"]["qloo_cached"] > 0

    def scores(page):
        return [(v["name"], v["fit"], v["lift"], v["confidence"], v["best_product"]["name"]) for v in page["items"]]

    a = (await client.get(f"/v1/runs/{first}/venues", headers=ws)).json()
    b = (await client.get(f"/v1/runs/{second}/venues", headers=ws)).json()
    assert scores(a) == scores(b)


async def test_sse_replays_from_last_event_id(client, ws, svc):
    """AGT-04: all events stream; reconnecting with Last-Event-ID replays only newer events."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)

    token = (await client.post(f"/v1/runs/{run_id}/events-token", headers=ws)).json()["token"]

    async def read(headers):
        out = []
        async with client.stream("GET", f"/v1/runs/{run_id}/events", headers=headers, params={"token": token}) as r:
            event = {}
            async for line in r.aiter_lines():
                if line.startswith("id:"):
                    event["id"] = int(line[3:].strip())
                elif line.startswith("event:"):
                    event["event"] = line[6:].strip()
                elif line == "" and event:
                    out.append(event)
                    event = {}
        return out

    events = await read(ws)
    types = [e["event"] for e in events]
    assert types[0] == "phase_started" and types[-1] == "end"
    assert {"tool_call", "step_done", "qloo_call", "phase_done"} <= set(types)
    ids = [e["id"] for e in events if "id" in e]
    mid = ids[len(ids) // 2]
    replay = await read({"Last-Event-ID": str(mid)})
    assert [e["id"] for e in replay if "id" in e] == [i for i in ids if i > mid]


async def test_rescore_changes_order_without_qloo_calls(client, ws, svc, fake_qloo):
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    n = len(fake_qloo.requests)
    r = await client.post(f"/v1/runs/{run_id}/rescore", headers=ws, json={"target": 0.0, "lift": 1.0})
    assert r.status_code == 200
    items = r.json()["items"]
    lifts = [max(v["lift"], 0) for v in items]
    assert lifts == sorted(lifts, reverse=True)
    assert len(fake_qloo.requests) == n


async def test_rescore_keeps_the_popularity_baseline_for_old_runs(client, ws, svc):
    """RNK-08: /rescore only re-weights stored percentiles, so old runs keep their numbers; scoring a run whose stored
    calls are target + popularity baseline (before D-23, or a pack with no generic brands) uses the old method."""
    from tasteroute_api.agent.context import RunContext
    from tasteroute_api.agent.tools import score_from_stored
    from tasteroute_api.categories import default_pack
    from tasteroute_api.qloo.client import stored_response
    from tasteroute_api.qloo.guards import guard_places
    from tasteroute_api.qloo.models import InsightsBody
    from tasteroute_api.scoring import rank

    run_id = await scout(client, ws, await make_brand(client, ws, svc))
    rid = uuid.UUID(run_id)
    st = await svc.pool.fetchval("select settings from runs where id = $1", rid)
    assert st["calls"]["cafe"].keys() == {"target", "generic"}  # new runs: mass-market taste
    st["calls"] = {"cafe": {"target": st["calls"]["cafe"]["target"], "baseline": st["calls"]["cafe"]["target"]}}
    await svc.pool.execute("update runs set settings = $2 where id = $1", rid, st)
    before = await svc.pool.fetch("select venue_id, target_pct, lift from venue_scores where run_id = $1 order by venue_id", rid)
    r = await client.post(f"/v1/runs/{run_id}/rescore", headers=ws, json={"target": 0.4, "lift": 0.6})
    assert r.status_code == 200 and before == await svc.pool.fetch(
        "select venue_id, target_pct, lift from venue_scores where run_id = $1 order by venue_id", rid)
    ctx = await RunContext.load(svc, run_id)
    ctx.settings_json["weights"] = {"target": 0.7, "lift": 0.3}
    await score_from_stored(ctx, emit_warnings=False)
    assert all(v["popularity_pct"] is None for v in (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"])

    tags = default_pack().venue_type("cafe").qloo_tags
    kept = guard_places(InsightsBody.model_validate(await stored_response(svc.pool, st["calls"]["cafe"]["target"]))
                        .results.entities, required_tags=tags, bbox=BROOKLYN["bbox"]).kept
    cands = [rank.Candidate(p.entity_id, p.affinity, p.popularity, rank.support([(x.entity_id, x.score) for x in p.explain()]))
             for p in kept]
    want = {s.venue_id: s.fit for s in rank.score_type("cafe", cands, [p.entity_id for p in kept],
                                                        {p.entity_id: p.popularity for p in kept}, signals=len(st["signal"]))}
    got = {x["qloo_entity_id"]: float(x["fit"]) for x in await svc.pool.fetch(
        "select v.qloo_entity_id, vs.fit from venue_scores vs join venues v on v.id = vs.venue_id where vs.run_id = $1", rid)}
    assert got and all(got[k] == want[k] for k in got)


async def test_llm_ranking_is_stored_and_never_changes_fit(client, ws, svc):
    """EVL-06: one LLM call ranks the run's venues from names, types and neighbourhoods, without the brand's name. It is
    stored (a second request makes no call) and fit and rank are unchanged."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    n = await svc.pool.fetchval("select count(*) from venue_scores where run_id = $1", uuid.UUID(run_id))
    before = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()
    assert all(v["llm_rank"] is None for v in before["items"])
    reply = json.dumps({"scores": [{"id": f"v{j}", "score": j % 100} for j in range(n)]})
    svc.llm.provider.script = [LLMResult(content=reply, model="fake-1", provider="fake")]
    after = (await client.post(f"/v1/runs/{run_id}/llm-ranking", headers=ws)).json()
    calls = len(svc.llm.provider.calls)
    prompt = svc.llm.provider.calls[-1]["messages"][-1]["content"]
    assert BRAND["name"] not in prompt and "Venues:" in prompt
    assert [(v["venue_id"], v["fit"], v["rank"]) for v in after["items"]] == \
        [(v["venue_id"], v["fit"], v["rank"]) for v in before["items"]]
    ranks = [v["llm_rank"] for v in after["items"]]
    assert all(isinstance(x, int) for x in ranks) and len(set(ranks)) == len(ranks)
    again = (await client.post(f"/v1/runs/{run_id}/llm-ranking", headers=ws)).json()
    assert len(svc.llm.provider.calls) == calls and [v["llm_rank"] for v in again["items"]] == ranks


async def test_chains_are_hidden_and_counted_and_cafes_lead_with_a_dry_product(client, ws, svc):
    """RNK-09: chain venues leave the default list and are counted; with show_hidden they come back after the rest.
    At a café, an alcoholic product never leads when a non-alcoholic one was scored."""
    brand = await make_brand(client, ws, svc)
    pid = brand["product_ids"][-1]
    await svc.pool.execute("update products set kind = 'aperitivo' where id = $1", uuid.UUID(pid))
    run_id = await scout(client, ws, brand)
    page = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()
    every = (await client.get(f"/v1/runs/{run_id}/venues?show_hidden=true", headers=ws)).json()
    hidden = [v for v in every["items"] if {"chain", "signal_brand_venue"} & set(v["flags"])]
    assert page["hidden"].get("chain") and len(every["items"]) - len(page["items"]) == len(hidden)
    assert not any({"chain", "signal_brand_venue"} & set(v["flags"]) for v in page["items"])
    assert [v["rank"] for v in page["items"]] == list(range(1, len(page["items"]) + 1))
    assert all(v["best_product"]["product_id"] != pid for v in every["items"] if v["best_product"])
    warnings = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()["warnings"]
    assert any("chain venues" in w for w in warnings)


async def test_outreach_contacts_drafts_approve_export(client, ws, svc):
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    venues = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"]
    top = [v["venue_id"] for v in venues[:6]]
    r = await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": top})
    assert r.status_code == 202, r.text
    await run_service.drain()
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "done", run

    contacts = (await client.get(f"/v1/runs/{run_id}/contacts", headers=ws)).json()
    assert {c["venue_id"] for c in contacts} == set(top)
    assert any(c["website"] for c in contacts)  # the outreach page links the venue's site
    # Live progress: a 'checking' and a 'done' event per venue, counting up to the total
    ev = [json.loads(e["payload"]) if isinstance(e["payload"], str) else e["payload"] for e in await svc.pool.fetch(
        "select payload from run_events where run_id = $1 and type = 'venue' order by id", uuid.UUID(run_id))]
    found_done = [e for e in ev if e["tool"] == "find_contacts" and e["state"] == "done"]
    assert [e["done"] for e in found_done] == list(range(1, len(top) + 1)) and found_done[-1]["of"] == len(top)
    assert all(e["result"] in ("found", "none", "limit_reached", "suppressed", "skipped_social") for e in found_done)
    drafted = [e for e in ev if e["tool"] == "draft_pitches" and e["state"] == "done"]
    assert drafted and drafted[-1]["done"] == drafted[-1]["of"]
    found = [c for c in contacts if c["status"] == "found"]
    assert found
    for c in found:  # CON-05: every stored email has a source
        assert all(x["source"] in ("osm", "website", "hunter") and x["sources"] for x in c["contacts"])

    drafts = (await client.get(f"/v1/runs/{run_id}/drafts", headers=ws)).json()
    assert {d["venue_id"] for d in drafts} == {c["venue_id"] for c in found}  # DRF-01
    opt_out = svc.settings.opt_out_line
    for d in drafts:
        assert d["source"] == "template"  # FakeProvider returns no valid JSON -> repair -> template (DRF-03)
        assert opt_out in d["body"]  # DRF-05
        assert d["mailto"] is None  # EXP-01: only approved drafts get a mailto

    d0 = drafts[0]
    r = await client.patch(f"/v1/drafts/{d0['id']}", headers=ws, json={"body": d0["body"] + "\nP.S. edited", "status": "approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert r.json()["mailto"].startswith("mailto:")
    again = (await client.get(f"/v1/runs/{run_id}/drafts", headers=ws)).json()
    assert next(d for d in again if d["id"] == d0["id"])["body"].endswith("P.S. edited")  # DRF-06

    # Regenerating keeps one draft per (run, venue, contact) and never touches approved drafts (REL-03)
    r = await client.post(f"/v1/runs/{run_id}/drafts", headers=ws, json={"venue_ids": top})
    assert r.status_code == 202
    await run_service.drain()
    after = (await client.get(f"/v1/runs/{run_id}/drafts", headers=ws)).json()
    assert len(after) == len(drafts)
    assert next(d for d in after if d["id"] == d0["id"])["status"] == "approved"
    r = await client.post(f"/v1/drafts/{d0['id']}/regenerate", headers=ws)
    assert r.status_code == 409 and r.json()["code"] == "draft_locked"

    r = await client.get(f"/v1/runs/{run_id}/export.csv", headers=ws)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    approved = [x for x in rows if x["draft_body"]]
    assert len(approved) == 1 and approved[0]["draft_status"] == "approved"  # EXP-01 approved-only
    exported = (await client.get(f"/v1/runs/{run_id}/drafts", headers=ws)).json()
    assert next(d for d in exported if d["id"] == d0["id"])["status"] == "exported"

    # Editing an exported draft sends it back to 'edited' (DRF-04)
    r = await client.patch(f"/v1/drafts/{d0['id']}", headers=ws, json={"subject": "New subject"})
    assert r.json()["status"] == "edited" and r.json()["mailto"] is None


async def test_outreach_evidence_links_its_call_and_never_duplicates(client, ws, svc):
    """EVD-04: OpenStreetMap and contact-source evidence name the external call they came from; a second outreach pass
    over the same venues replaces those rows instead of adding more."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    top = [v["venue_id"] for v in (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"][:4]]
    for _ in range(2):
        r = await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": top})
        assert r.status_code == 202, r.text
        await run_service.drain()
    rows = await svc.pool.fetch(
        "select e.venue_id, e.type, e.source_call_id, x.id as call from venue_evidence e left join external_calls x "
        "on x.id = e.source_call_id where e.run_id = $1 and e.type in ('osm_fact', 'contact_source')", uuid.UUID(run_id))
    assert {r["type"] for r in rows} == {"osm_fact", "contact_source"}
    assert all(r["call"] is not None for r in rows), rows  # each id is a real external_calls row
    assert len({(r["venue_id"], r["type"]) for r in rows}) == len(rows)


async def test_web_search_is_the_last_resort_for_an_email(client, ws, svc, net, monkeypatch):
    """No address on the venues' own pages: Ollama web search. Each result page is fetched (snippets aren't trusted) and
    only the venue's own address read on it is kept (CON-08)."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    venues = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"]
    monkeypatch.setattr("tests.conftest.SITE", "<html><body><h1>{host}</h1><p>Coffee and natural wine.</p></body></html>")
    monkeypatch.setattr(svc.settings, "ollama_api_key", SecretStr("k"))

    def results(request: httpx.Request) -> httpx.Response:
        name = json.loads(request.content)["query"].split('"')[1]
        handle = re.sub(r"[^a-z0-9]", "", name.lower())
        return httpx.Response(200, json={"results": [{"title": name, "url": "https://dir.test/" + handle,
                                                      "content": f"{name}: write to {handle}@yahoo.com"}]})  # snippet only

    def listing(request: httpx.Request) -> httpx.Response:  # the directory page each result points at
        if request.url.host != "dir.test" or request.url.path == "/robots.txt":
            return conftest.fake_site(request)
        handle = request.url.path.strip("/")
        return httpx.Response(200, html=f"<p>{handle}: write to {handle}@gmail.com or ads@dir.test</p>")

    net.routes[-1].side_effect = listing  # the catch-all site route
    net["web_search"].side_effect = results
    pick = [v["venue_id"] for v in venues[:3]]
    await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": pick})
    await run_service.drain()
    contacts = (await client.get(f"/v1/runs/{run_id}/contacts", headers=ws)).json()
    web = [c for c in contacts if "web search" in c["checked_sources"]]
    assert web and net["web_search"].called
    for c in web:  # no OpenStreetMap or page address: the web found the venue's own inbox, never the directory's
        assert [(x["source"], x["sources"][0]["found_by"]) for x in c["contacts"]] == [("web", "web_search")]
        assert all(x["email"].endswith("@gmail.com") for x in c["contacts"])  # read on the page, not the snippet


async def test_cancel_stops_outreach(client, ws, svc, monkeypatch):
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    venues = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"]
    started, stopped = asyncio.Event(), asyncio.Event()

    async def slow_phase(*_: object) -> None:  # an outreach that would run for an hour
        started.set()
        try:
            await asyncio.sleep(3600)
        finally:
            stopped.set()

    monkeypatch.setattr(run_service, "run_phase", slow_phase)
    r = await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": [venues[0]["venue_id"]]})
    assert r.json()["status"] == "outreach_running"
    assert (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()["status"] == "outreach_running"  # before any work ran
    await asyncio.wait_for(started.wait(), 5)
    r = await client.post(f"/v1/runs/{run_id}/cancel", headers=ws)
    assert r.status_code == 202 and r.json()["status"] == "scouted"
    assert stopped.is_set()  # the background work stopped, not just the status
    await run_service.drain()
    run = (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()
    assert run["status"] == "scouted" and run["error_code"] == "cancelled"
    assert (await client.post(f"/v1/runs/{run_id}/cancel", headers=ws)).json()["status"] == "scouted"  # nothing running: no-op

    # A run left 'outreach_running' by an API restart has no task; cancel still frees it
    await svc.pool.execute("update runs set status = 'outreach_running' where id = $1", uuid.UUID(run_id))
    assert (await client.post(f"/v1/runs/{run_id}/cancel", headers=ws)).json()["status"] == "scouted"
    assert (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()["status"] == "scouted"


async def test_suppression_hides_contacts_drafts_and_export(client, ws, svc):
    """CON-07, EXP-03."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    venues = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"]
    await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": [v["venue_id"] for v in venues[:6]]})
    await run_service.drain()
    drafts = (await client.get(f"/v1/runs/{run_id}/drafts", headers=ws)).json()
    victim = drafts[0]["contact_email"]
    domain = victim.split("@")[1]
    r = await client.post("/v1/suppressions", headers=ws, json={"kind": "domain", "value": f"https://www.{domain}/"})
    assert r.status_code == 201 and r.json()["value"] == domain
    after = (await client.get(f"/v1/runs/{run_id}/drafts", headers=ws)).json()
    assert victim not in {d["contact_email"] for d in after}
    csv_text = (await client.get(f"/v1/runs/{run_id}/export.csv", headers=ws)).text
    assert victim not in csv_text
    r = await client.patch(f"/v1/drafts/{drafts[0]['id']}", headers=ws, json={"status": "approved"})
    assert r.status_code == 409
    sid = r and (await client.get("/v1/suppressions", headers=ws)).json()[0]["id"]
    assert (await client.delete(f"/v1/suppressions/{sid}", headers=ws)).status_code == 204
    assert (await client.get("/v1/suppressions", headers=ws)).json() == []
    bad = await client.post("/v1/suppressions", headers=ws, json={"kind": "email", "value": "not-an-email"})
    assert bad.status_code == 422


async def test_brand_edits_persist(client, ws, svc):
    """INT-05."""
    brand = await make_brand(client, ws, svc, resolve=False)
    r = await client.patch(f"/v1/brands/{brand['brand_id']}", headers=ws, json={"name": "Fieldnote Roasters"})
    assert r.status_code == 200 and r.json()["name"] == "Fieldnote Roasters"
    got = (await client.get(f"/v1/brands/{brand['brand_id']}", headers=ws)).json()
    assert got["name"] == "Fieldnote Roasters" and [p["name"] for p in got["products"]] == [p["name"] for p in BRAND["products"]]
