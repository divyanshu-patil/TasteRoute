"""Does lift change the list? (score plan C1, RNK-07). For runs with stored target and popularity-baseline calls, makes
the mass-market call per venue type (1 live Qloo call each, then cached) and compares three orders of the same venues:
taste only (fit = target percentile), the old popularity lift, and the new mass-market lift.

    uv run python scripts/lift_effect.py <run_id> [<run_id> ...]
"""

import asyncio
import statistics
import sys
import uuid

from tasteroute_api import db
from tasteroute_api.agent.context import RunContext
from tasteroute_api.agent.tools import load_places
from tasteroute_api.evaluation import jaccard, spearman
from tasteroute_api.main import build_services, close_services
from tasteroute_api.qloo import api
from tasteroute_api.qloo.guards import guard_places
from tasteroute_api.scoring import rank
from tasteroute_api.settings import get_settings

TOP = 15


def order(rows: list[rank.Scored]) -> list[str]:
    return [s.venue_id for s in rank.merge([rows], 10_000)]


async def one(svc, run_id: str) -> list[str]:
    ctx = await RunContext.load(svc, run_id)
    generic_ids = ctx.pack.baseline_entities
    signals = len(ctx.settings_json.get("signal") or []) or 2
    taste, old, new, lifts_old, lifts_new = [], [], [], [], []
    for vt, c in ctx.settings_json["calls"].items():
        if "baseline" not in c:
            continue
        tags = ctx.pack.venue_type(vt).qloo_tags
        target = await load_places(ctx, c["target"])
        kept = guard_places(target.results.entities, required_tags=tags, bbox=ctx.city.get("bbox")).kept
        base = guard_places((await load_places(ctx, c["baseline"])).results.entities, required_tags=tags,
                            bbox=ctx.city.get("bbox")).kept
        body, _, hit = await api.place_insights(svc.qloo, results_ids=[p.entity_id for p in target.results.entities],
                                                signal_ids=generic_ids)
        generic = {p.entity_id: p.affinity for p in body.results.entities if p.affinity is not None}
        cands = [rank.Candidate(p.entity_id, p.affinity, p.popularity, rank.support([(x.entity_id, x.score) for x in p.explain()]))
                 for p in kept]
        taste += rank.score_type(vt, cands, [], {}, rank.Weights(1.0, 0.0), signals=signals)
        o = rank.score_type(vt, cands, [p.entity_id for p in base], {p.entity_id: p.popularity for p in base}, signals=signals)
        n = rank.score_against_generic(vt, cands, generic, signals=signals)
        old += o
        new += n
        lifts_old += [s.lift for s in o]
        lifts_new += [s.lift for s in n]
        print(f"  {vt}: {len(kept)} venues, generic call {'cached' if hit else 'live'}, "
              f"{sum(1 for p in kept if p.entity_id not in generic)} without a generic reading")
    t, o, n = order(taste), order(old), order(new)
    name = ctx.brand["name"]
    return [
        f"| {name} | {len(t)} | {statistics.pstdev(lifts_old):.3f} | {statistics.pstdev(lifts_new):.3f} | "
        f"{spearman(o, t)} | {spearman(n, t)} | {jaccard(o[:TOP], t[:TOP])} | {jaccard(n[:TOP], t[:TOP])} | "
        f"{jaccard(o[:TOP], n[:TOP])} |"
    ]


async def main(run_ids: list[str]) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    svc = build_services(s, pool)
    try:
        t0 = await pool.fetchval("select now()")
        rows = []
        for r in run_ids:
            print(r)
            rows += await one(svc, r)
        print("\n| Brand | Venues | Lift spread, popularity (sd) | Lift spread, mass-market (sd) | Spearman popularity-lift "
              "vs taste only | Spearman mass-market-lift vs taste only | Top-15 Jaccard popularity-lift vs taste only | "
              "Top-15 Jaccard mass-market-lift vs taste only | Top-15 Jaccard popularity vs mass-market |")
        print("|---|---|---|---|---|---|---|---|---|")
        print("\n".join(rows))
        live = await pool.fetchval("select count(*) from qloo_calls where not cache_hit and created_at >= $1", t0)
        print(f"\nlive Qloo calls spent: {live}")
    finally:
        await close_services(svc)
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main([str(uuid.UUID(a)) for a in sys.argv[1:]]))
