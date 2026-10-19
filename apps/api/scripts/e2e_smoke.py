"""End-to-end check of the judge path over HTTP, exactly as the web app calls the API.
Spends live calls (about 10 Qloo, 15-25 LLM, a few OSM and venue-site reads); prints what it spent.

    uv run python scripts/e2e_smoke.py [--api http://localhost:8000] [--city Brooklyn]
"""

import argparse
import asyncio
import csv
import io
import sys
import time

import httpx

DESCRIPTION = (
    "Brine & Barrel is a tiny Brooklyn pickle shop. We make small-batch garlic dill pickles, spicy pickled carrots "
    "and a pickle-brine Bloody Mary mix, and we want to sell to bars, delis and cafés."
)
failures: list[str] = []


def check(ok: bool, what: str) -> bool:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)
    return ok


async def wait_for(c: httpx.AsyncClient, run_id: str, done: set[str], timeout: float = 420) -> dict:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        run = (await c.get(f"/v1/runs/{run_id}")).json()
        if run["status"] in done | {"failed"}:
            return run
        await asyncio.sleep(3)
    return run


async def main(api: str, city_q: str) -> None:
    async with httpx.AsyncClient(base_url=api, timeout=120) as c:
        h = (await c.get("/health")).json()
        check(h["status"] == "ok" and h["qloo"] == "ok", f"health: db {h['db']}, qloo {h['qloo']}, llm {h['llm']['provider']}")

        token = (await c.post("/v1/workspaces/session", json={})).json()["workspace_token"]
        c.headers["X-Workspace-Token"] = token

        # Sample run: public, read-only
        demo = (await c.get("/v1/demo")).json()
        if check(demo["available"], "sample run available"):
            page = (await c.get(f"/v1/runs/{demo['run_id']}/venues", params={"limit": 100})).json()
            check(page["total"] >= 15, f"sample ranks {page['total']} venues")
            drafts = (await c.get(f"/v1/runs/{demo['run_id']}/drafts")).json()
            if drafts:
                r = await c.patch(f"/v1/drafts/{drafts[0]['id']}", json={"status": "approved"})
                check(r.status_code in (401, 403, 404, 409), f"sample drafts are read-only ({r.status_code})")

        # 01 brand → 02 profile
        intake = (await c.post("/v1/brands/intake", json={"description": DESCRIPTION})).json()
        prof = intake["profile"]
        prods = [{k: p.get(k) or "" for k in ("name", "kind", "notes")} for p in prof.get("products") or []]
        check(bool(prods), f"intake drafted {prof.get('brand_name')!r} with products {[p['name'] for p in prods]}")
        keys = ("category", "one_liner", "price_tier", "prospects_are_consumer_facing", "style_words", "unsupported_reason")
        profile = {**{k: prof.get(k) for k in keys}, "sender_name": "Sam at Brine & Barrel"}
        r = await c.post("/v1/brands", json={"name": prof.get("brand_name") or "Brine & Barrel", "profile": profile,
                                             "products": prods[:3], "source_text": intake.get("source_text")})
        check(r.status_code == 201, f"brand saved ({r.status_code})")
        brand_id = r.json()["brand_id"]

        # 03 Qloo matches: resolve, then add one brand by search
        res = (await c.post(f"/v1/brands/{brand_id}/resolve")).json()
        for x in res:
            print(f"     {x['status']}: {[e['name'] for e in x['entities']]} dropped {x['dropped']}")
        check(any(x["entities"] for x in res), "at least one product has Qloo entities")
        found = (await c.get("/v1/qloo/search", params={"q": "Grillo's Pickles"})).json()
        if check(bool(found), f"Qloo search found {[f['name'] for f in found[:3]]}"):
            pid, add = res[0]["product_id"], found[0]
            keep = [{"entity_id": e["entity_id"], "source_call_id": e.get("source_call_id") or ""} for e in res[0]["entities"]]
            out = (await c.put(f"/v1/products/{pid}/entities",
                               json={"entities": keep + [{"entity_id": add["entity_id"], "source_call_id": add["source_call_id"]}]})).json()
            check(any(e["entity_id"] == add["entity_id"] for e in out), f"added {add['name']} to {prods[0]['name']}")

        # 04 city → run
        city = (await c.get("/v1/cities/search", params={"q": city_q})).json()[0]
        r = await c.post("/v1/runs", json={"brand_id": brand_id, "product_ids": [x["product_id"] for x in res],
                                           "city": city, "venue_types": ["cafe", "bar"]})
        if not check(r.status_code == 202, f"run started in {city['display_name'][:40]} ({r.status_code})"):
            sys.exit("daily run limit reached: raise PUBLIC_RUNS_PER_IP_PER_DAY on the API to test again" if r.status_code == 429
                     else r.text)
        run_id = r.json()["run_id"]
        run = await wait_for(c, run_id, {"scouted"})
        check(run["status"] == "scouted", f"scout {run['status']} via {run['orchestration']} ({run.get('error_code')})")

        page = (await c.get(f"/v1/runs/{run_id}/venues", params={"limit": 100})).json()
        rows = page["items"]
        check(len(rows) >= 15, f"{page['total']} venues ranked")
        check([v["fit"] for v in rows] == sorted((v["fit"] for v in rows), reverse=True), "sorted by fit")
        conf = {k: sum(v["confidence"] == k for v in rows) for k in ("high", "medium", "low")}
        check(conf["high"] > 0, f"confidence mix {conf}")
        check(all(v["reason"] for v in rows[:10]), "top 10 have reasons")
        detail = (await c.get(f"/v1/runs/{run_id}/venues/{rows[0]['venue_id']}")).json()
        kinds = {e["type"] for e in detail["evidence"]}
        check({"qloo_affinity", "qloo_explanation"} <= kinds, f"#1 {rows[0]['name']} evidence: {sorted(kinds)}")
        moved = (await c.post(f"/v1/runs/{run_id}/rescore", json={"target": 0.9, "lift": 0.1})).json()["items"]
        check(len(moved) == len(rows), "rescore without new calls")
        await c.post(f"/v1/runs/{run_id}/rescore", json={"target": 0.7, "lift": 0.3})

        # Outreach: contacts and drafts for the top 6
        top = [v["venue_id"] for v in rows[:6]]
        r = await c.post(f"/v1/runs/{run_id}/contacts", json={"venue_ids": top})
        check(r.status_code in (200, 202), f"outreach started ({r.status_code})")
        run = await wait_for(c, run_id, {"done"})
        check(run["status"] == "done", f"outreach {run['status']} via {run['orchestration']}")
        contacts = (await c.get(f"/v1/runs/{run_id}/contacts")).json()
        with_email = [x for x in contacts if x["contacts"]]
        for x in contacts:
            print(f"     {x['name'][:32]:32} {x['status']:10} {x['contacts'][0]['email'] if x['contacts'] else ''}")
        check(all(x["checked_sources"] for x in contacts), f"{len(with_email)} of {len(contacts)} have a public email; all list sources")
        drafts = (await c.get(f"/v1/runs/{run_id}/drafts")).json()
        check(len(drafts) == len(with_email), f"{len(drafts)} drafts ({sorted({d['source'] for d in drafts})})")
        if drafts:
            d = drafts[0]
            r = await c.patch(f"/v1/drafts/{d['id']}", json={"body": d["body"] + "\n\nThanks!"})
            check(r.status_code == 200 and r.json()["body"].endswith("Thanks!"), "draft edited")
            r = await c.patch(f"/v1/drafts/{d['id']}", json={"status": "approved"})
            check(r.status_code == 200 and r.json()["status"] == "approved", "draft approved")
            check(not d["mailto"] and (r.json()["mailto"] or "").startswith("mailto:"), "mail link appears only after approval")
            text = (await c.get(f"/v1/runs/{run_id}/export.csv")).text
            exported = list(csv.DictReader(io.StringIO(text)))
            check(any(x.get("draft_status") == "approved" for x in exported), f"CSV export has {len(exported)} rows incl. the approved draft")

            dom = d["contact_email"].rsplit("@", 1)[1]
            s = (await c.post("/v1/suppressions", json={"kind": "domain", "value": dom, "reason": "manual"})).json()
            again = (await c.get(f"/v1/runs/{run_id}/export.csv")).text
            check(dom not in again, f"do-not-contact {dom} removed from export")
            await c.delete(f"/v1/suppressions/{s['id']}")

        trace = (await c.get(f"/v1/runs/{run_id}/trace")).json()
        check({t["kind"] for t in trace} >= {"qloo", "llm", "tool"}, f"trace has {len(trace)} rows: {sorted({t['kind'] for t in trace})}")
        run = (await c.get(f"/v1/runs/{run_id}")).json()
        print(f"\nrun {run_id}\nlive calls: {run['counters']}")
    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILED: ' + '; '.join(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--city", default="Brooklyn")
    a = ap.parse_args()
    asyncio.run(main(a.api, a.city))
