"""Seed the read-only sample run with REAL Qloo, Ollama Cloud and OSM calls (F10). Spends live calls.

uv run python scripts/seed_demo.py [--outreach 8]
uv run python scripts/seed_demo.py --redraft RUN_ID   # rewrite the drafts of an existing sample's contacted venues
Prints the run id for DEMO_RUN_ID and how many live calls were spent.
"""

import argparse
import asyncio
import uuid

from tasteroute_api import db
from tasteroute_api.categories import pack_for
from tasteroute_api.main import Services, build_services, close_services
from tasteroute_api.qloo.client import Trace
from tasteroute_api.scoring import SCORING_VERSION
from tasteroute_api.services import compare
from tasteroute_api.services import runs as run_service
from tasteroute_api.services.intake import propose
from tasteroute_api.services.resolve import resolve_product
from tasteroute_api.settings import get_settings

# D-10: a fictional brand, entered by description; its products resolve through real comparables.
BRAND = "Fieldnote Drinks Co."
SENDER = "Sam"
DESCRIPTION = (
    "Fieldnote Drinks Co. is a small Brooklyn maker of craft drinks for cafés and bars: a slow-steeped nitro cold brew, "
    "a raw ginger kombucha, and a bitter-orange aperitivo for spritzes. Small-batch, premium, made in Red Hook."
)
PRODUCTS = [
    {"name": "Nitro Cold Brew", "kind": "cold brew coffee"},
    {"name": "Ginger Kombucha", "kind": "kombucha"},
    {"name": "Bitter Orange Aperitivo", "kind": "aperitivo liqueur"},
]
CITY = {"name": "Brooklyn", "display_name": "Brooklyn, Kings County, New York, United States", "country": "us",
        "lat": 40.6526006, "lon": -73.9497211, "bbox": [40.5503390, -74.0566880, 40.7394340, -73.8329450],
        "qloo_query": "Brooklyn"}
# The fictional brand's location: a neighbourhood point, not a real address. Shows distances; never changes ranking.
BASE = {"label": "Greenpoint", "detail": "Brooklyn, New York, United States", "lat": 40.7304, "lon": -73.9515}
TYPES = ["cafe", "bar"]


async def redraft(svc: Services, run_id: str) -> None:
    """After a prompt or sender change: same venues, contacts and evidence, new drafts."""
    pool = svc.pool
    await pool.execute("update brands set profile = profile || $2 where id = (select brand_id from runs where id = $1)",
                       uuid.UUID(run_id), {"sender_name": SENDER})
    ids = [str(r["venue_id"]) for r in await pool.fetch("select distinct venue_id from drafts where run_id = $1", uuid.UUID(run_id))]
    await run_service.run_outreach(svc, run_id, ids, drafts_only=True)
    print(f"redrafted {len(ids)} venues")


async def main(outreach: int, redo: str | None) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    svc = build_services(s, pool)
    try:
        t0 = await pool.fetchval("select now()")
        if redo:
            await redraft(svc, redo)
            print("llm calls:", await pool.fetchval("select count(*) from llm_calls where created_at >= $1", t0))
            return
        ws = await pool.fetchval("select id from workspaces where kind = 'demo' order by created_at limit 1") \
            or await pool.fetchval("insert into workspaces (kind) values ('demo') returning id")
        proposal = await propose(svc, None, DESCRIPTION)
        profile = {**proposal["profile"], "sender_name": SENDER}
        profile.pop("products", None)
        profile.pop("brand_name", None)
        pack = pack_for("food_drink" if profile.get("category") != "fashion" else "fashion")
        profile["category"] = pack.id
        brand_id = await pool.fetchval(
            "insert into brands (workspace_id, name, category, profile, confirmed_at) values ($1,$2,$3,$4, now()) returning id",
            ws, BRAND, pack.id, profile)
        brand = dict(await pool.fetchrow("select * from brands where id = $1", brand_id))
        pids = []
        for i, p in enumerate(PRODUCTS):
            pid = await pool.fetchval(
                "insert into products (workspace_id, brand_id, name, kind, position) values ($1,$2,$3,$4,$5) returning id",
                ws, brand_id, p["name"], p["kind"], i)
            prod = dict(await pool.fetchrow("select * from products where id = $1", pid))
            res = await resolve_product(svc, brand, prod, pack, Trace(step="resolve_preview"))
            await pool.execute("update products set entities = $2 where id = $1", pid, res["entities"])
            print(f"  {p['name']}: {res['status']} -> {[e['name'] for e in res['entities']]} dropped={res['dropped']}")
            pids.append(pid)
        run_id = await pool.fetchval(
            "insert into runs (workspace_id, brand_id, city, venue_types, scoring_version, settings) "
            "values ($1,$2,$3,$4,$5,$6) returning id",
            ws, brand_id, CITY, TYPES, SCORING_VERSION, {"weights": {"target": 0.7, "lift": 0.3}, "base": BASE})
        await pool.executemany("insert into run_products (run_id, product_id) values ($1,$2)", [(run_id, p) for p in pids])
        rid = str(run_id)
        await run_service.run_scout(svc, rid)
        run = await pool.fetchrow("select status, orchestration, orchestration_reason, error_code from runs where id = $1", run_id)
        print("scout:", dict(run))
        if run["status"] in ("scouted", "done"):  # the sample shows the LLM column without a click (EVL-06)
            ranks = await compare.llm_ranking(svc, rid)
            print(f"llm ranking: {len(ranks)} venues")
        if run["status"] == "scouted" and outreach:
            top = [str(r["venue_id"]) for r in await pool.fetch(
                "select venue_id from venue_scores where run_id = $1 order by rank limit $2", run_id, outreach)]
            await run_service.run_outreach(svc, rid, top)
            run = await pool.fetchrow("select status, orchestration, orchestration_reason, counters from runs where id = $1", run_id)
            print("outreach:", dict(run))
        spent = await pool.fetchrow(
            "select (select count(*) from qloo_calls where not cache_hit and created_at >= $1) qloo, "
            "(select count(*) from llm_calls where created_at >= $1) llm, "
            "(select coalesce(json_object_agg(service, n), '{}') from (select service, count(*) n from external_calls "
            " where not cache_hit and created_at >= $1 group by service) x) external", t0)
        print(f"\nDEMO_RUN_ID={rid}\nlive calls spent: {dict(spent)}")
    finally:
        await close_services(svc)
        await db.close_pool()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--outreach", type=int, default=8, help="top venues to find contacts and drafts for")
    ap.add_argument("--redraft", metavar="RUN_ID", help="only rewrite the drafts of this existing run")
    a = ap.parse_args()
    asyncio.run(main(a.outreach, a.redraft))
