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
from tasteroute_api.services import runs as run_service

from ..conftest import BRAND, SPECIALTY, make_brand, scout


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
    assert {"qloo_affinity", "qloo_venue_profile", "inference"} <= kinds
    assert all(e["source_kind"] == "inference" for e in detail["evidence"] if e["type"] == "inference")  # EVD-03

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


async def test_web_search_is_the_last_resort_for_an_email(client, ws, svc, net, monkeypatch):
    """No address on the venues' own pages (and the AI finds none): Ollama web search, keeping only the venue's own."""
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    venues = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"]
    monkeypatch.setattr("tests.conftest.SITE", "<html><body><h1>{host}</h1><p>Coffee and natural wine.</p></body></html>")
    monkeypatch.setattr(svc.settings, "ollama_api_key", SecretStr("k"))

    def results(request: httpx.Request) -> httpx.Response:
        name = json.loads(request.content)["query"].split('"')[1]
        handle = re.sub(r"[^a-z0-9]", "", name.lower())
        return httpx.Response(200, json={"results": [{"title": name, "url": "https://dir.test/" + handle,
                                                      "content": f"{name}: write to {handle}@gmail.com or ads@dir.test"}]})

    net["web_search"].side_effect = results
    pick = [v["venue_id"] for v in venues[:3]]
    await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": pick})
    await run_service.drain()
    contacts = (await client.get(f"/v1/runs/{run_id}/contacts", headers=ws)).json()
    web = [c for c in contacts if "web search" in c["checked_sources"]]
    assert web and net["web_search"].called
    for c in web:  # no OpenStreetMap or page address: the web found the venue's own inbox, never the directory's
        assert "venue website (read by AI)" in c["checked_sources"]
        assert [(x["source"], x["sources"][0]["found_by"]) for x in c["contacts"]] == [("web", "web_search")]
        assert not any(x["email"].endswith("@dir.test") for x in c["contacts"])


async def test_cancel_stops_outreach(client, ws, svc, monkeypatch):
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    venues = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"]
    stopped = asyncio.Event()

    async def slow_phase(*_: object) -> None:  # an outreach that would run for an hour
        try:
            await asyncio.sleep(3600)
        finally:
            stopped.set()

    monkeypatch.setattr(run_service, "run_phase", slow_phase)
    r = await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": [venues[0]["venue_id"]]})
    assert r.json()["status"] == "outreach_running"
    assert (await client.get(f"/v1/runs/{run_id}", headers=ws)).json()["status"] == "outreach_running"  # before any work ran
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
