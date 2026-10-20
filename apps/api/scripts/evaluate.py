"""Qloo-on vs Qloo-off evaluation (docs/15-evaluation.md). Spends live calls; Qloo baselines and Overpass are usually cached.

uv run python scripts/evaluate.py                                  # setups A, B, C -> docs/evaluation-results.md + pairs CSV
uv run python scripts/evaluate.py --score ../../docs/evaluation_pairs.csv   # after the judge fills `better_fit`

A = the app's ranking (taste, mass-market lift, fit). B = Qloo popularity baseline only. C = no Qloo: OpenStreetMap venues
ranked by the LLM from name, type and website. The blind-pair key is stored in the `evaluations` table, not in the CSV.
"""

import argparse
import asyncio
import csv
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from seed_demo import CITY, TYPES

from tasteroute_api import db
from tasteroute_api.categories import pack_for
from tasteroute_api.evaluation import a_wins, blind_pairs, jaccard, spearman
from tasteroute_api.external import osm
from tasteroute_api.llm.prompts import load
from tasteroute_api.llm.structured import structured
from tasteroute_api.main import build_services, close_services
from tasteroute_api.qloo import api
from tasteroute_api.qloo.client import Trace
from tasteroute_api.qloo.guards import guard_places
from tasteroute_api.scoring import rank
from tasteroute_api.services.drafts import short_name
from tasteroute_api.services.resolve import best_match
from tasteroute_api.settings import get_settings

ROOT = Path(__file__).resolve().parents[3]
REPORT, PAIRS = ROOT / "docs/evaluation-results.md", ROOT / "docs/evaluation_pairs.csv"
METHOD = "qloo_on_off_v1"
TOP, N_PAIRS, BATCH = 15, 10, 50

# Two fictional brands with clearly different tastes, each represented by real comparable brands Qloo knows.
BRANDS = [
    {"key": "coffee", "name": "Ridgeline Coffee Roasters",
     "about": "A small-batch specialty coffee roaster selling single-origin beans and cold brew to cafés and bars.",
     "comparables": ["Stumptown Coffee Roasters", "Blue Bottle Coffee", "La Colombe Coffee Roasters"]},
    {"key": "soda", "name": "Fizzbox Cola",
     "about": "A mainstream, low-price cola and lemon-lime soda in cans, for casual spots, sports bars and quick stops.",
     "comparables": ["Coca-Cola", "Pepsi", "Dr Pepper"]},
]


class Score(BaseModel):
    id: str
    score: int = Field(ge=0, le=100)


class Scores(BaseModel):
    scores: list[Score]


def venue(p: Any, vt: str) -> dict[str, Any]:
    loc = p.location
    return {"id": p.entity_id, "name": p.name, "type": vt, "lat": loc.lat if loc else None, "lon": loc.lon if loc else None,
            "website": p.properties.get("website") or "", "address": p.properties.get("address") or ""}


async def qloo_lists(svc: Any, pack: Any, b: dict[str, Any], trace: Trace) -> tuple[list[str], list[dict], list[dict]]:
    """Setup A (same scoring code as rank_venues) and setup B (baseline percentile only)."""
    ids, names = [], []
    for n in b["comparables"]:
        found, _ = await api.search(svc.qloo, n, pack.product_entity_types, trace)
        m = best_match(n, found)
        if m:
            ids.append(m[0].entity_id)
            names.append(m[0].name)
    per_type, base, places = [], [], {}
    for vt in TYPES:
        tags = pack.venue_type(vt).qloo_tags
        (t, _, _), (bl, _, _) = await asyncio.gather(
            api.place_insights(svc.qloo, city_query=CITY["qloo_query"], tags=tags, signal_ids=ids, explain=True, trace=trace),
            api.place_insights(svc.qloo, city_query=CITY["qloo_query"], tags=tags, trace=trace),
        )
        gt = guard_places(t.results.entities, required_tags=tags, bbox=CITY["bbox"])
        gb = guard_places(bl.results.entities, required_tags=tags, bbox=CITY["bbox"])
        cands = [rank.Candidate(p.entity_id, p.affinity, p.popularity, rank.support([(x.entity_id, x.score) for x in p.explain()]))
                 for p in gt.kept]
        # the same venues under mass-market brands, as rank_venues does (D-23)
        g, _, _ = await api.place_insights(svc.qloo, results_ids=[p.entity_id for p in t.results.entities],
                                           signal_ids=pack.baseline_entities, trace=trace)
        aff = {p.entity_id: p.affinity for p in g.results.entities if p.affinity is not None}
        per_type.append(rank.score_against_generic(vt, cands, aff))
        pct = rank.percentiles({p.entity_id: p.popularity for p in gb.kept})
        base += [(pct[p.entity_id], vt, p) for p in gb.kept]
        for p in gt.kept + gb.kept:
            places.setdefault(p.entity_id, venue(p, vt))
    a = [places[s.venue_id] | {"fit": s.fit, "lift": s.lift, "confidence": s.confidence} for s in rank.merge(per_type, TOP)]
    seen, b_list = set(), []
    for _, _, p in sorted(base, key=lambda x: -x[0]):
        if p.entity_id not in seen:
            seen.add(p.entity_id)
            b_list.append(places[p.entity_id])
    return names, a, b_list[:TOP]


async def llm_list(svc: Any, b: dict[str, Any], pool_c: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Setup C: the LLM scores OSM venues in batches; no Qloo data."""
    system, version = load("eval_rank_no_qloo")
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for start in range(0, len(pool_c), BATCH):
        batch = pool_c[start:start + BATCH]
        lines = "\n".join(f"v{i}: {v['name']} ({v['type']}) {v['website']}" for i, v in enumerate(batch))
        user = f"Brand: {b['name']}\nAbout: {b['about']}\nCity: Brooklyn, New York\n\nVenues:\n{lines}"
        out = await structured(svc.llm, Scores, system, user, purpose="evaluation", prompt_version=version,
                               temperature=0.0, max_tokens=3000)
        got = {s.id: s.score for s in out.scores}
        scored += [(got.get(f"v{i}", -1), start + i, v) for i, v in enumerate(batch)]
    return [v for _, _, v in sorted(scored, key=lambda x: (-x[0], x[1]))][:TOP]


def osm_key(v: dict[str, Any], elements: dict[str, list[dict]]) -> str:
    if str(v["id"]).startswith(("node/", "way/", "relation/")):
        return str(v["id"])
    # Qloo names often carry a suffix ("X - Coffee Shop & Roastery"); OSM extends names differently ("X (Brooklyn ...)").
    m = osm.match_osm(short_name(v["name"]), v["lat"], v["lon"], [e for els in elements.values() for e in els])
    return m["id"] if m else f"qloo:{v['id']}"


def ok(cond: bool) -> str:
    return "met" if cond else "**missed**"


def fmt(x: float | None) -> str:
    return "n/a (fewer than 3 shared)" if x is None else f"{x:.2f}"


async def evaluate(c_pool: int) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    svc = build_services(s, pool)
    try:
        t0 = await pool.fetchval("select now()")
        pack = pack_for("food_drink")
        trace = Trace(step="evaluate")
        elements: dict[str, list[dict]] = {}
        pool_c: list[dict[str, Any]] = []
        for vt in TYPES:
            o = pack.venue_type(vt).osm
            elements[vt], _ = await osm.venue_tags(pool, svc.http, s.overpass_base_url, s.osm_user_agent,
                                                   key=o.key, value=o.value, bbox=CITY["bbox"])
            named = sorted((e for e in elements[vt] if e["tags"].get("name")), key=lambda e: hashlib.sha1(e["id"].encode()).hexdigest())
            pool_c += [{"id": e["id"], "name": e["tags"]["name"], "type": vt, "lat": e["lat"], "lon": e["lon"],
                        "website": e["tags"].get("website") or e["tags"].get("contact:website") or "", "address": ""}
                       for e in named[:c_pool]]
        pool_keys = {v["id"] for v in pool_c}

        res: dict[str, dict[str, Any]] = {}
        for b in BRANDS:
            signal, a, bl = await qloo_lists(svc, pack, b, trace)
            c = await llm_list(svc, b, pool_c)
            ak, ck = [osm_key(v, elements) for v in a], [v["id"] for v in c]
            res[b["key"]] = {
                "signal": signal, "A": a, "B": bl, "C": c,
                "a_vs_b": jaccard([v["id"] for v in a], [v["id"] for v in bl]),
                "a_vs_b_rho": spearman([v["id"] for v in a], [v["id"] for v in bl]),
                "a_vs_c": jaccard(ak, ck), "a_vs_c_rho": spearman(ak, ck),
                "a_in_osm": sum(not k.startswith("qloo:") for k in ak), "a_in_pool": sum(k in pool_keys for k in ak),
                "a_only": [v for v, k in zip(a, ak, strict=True) if k not in set(ck)],
                "c_only": [v for v in c if v["id"] not in set(ak)],
            }
        r1, r2 = (res[b["key"]] for b in BRANDS)
        brand_a = jaccard([v["id"] for v in r1["A"]], [v["id"] for v in r2["A"]])
        brand_c = jaccard([v["id"] for v in r1["C"]], [v["id"] for v in r2["C"]])

        pairs, key = [], {}
        for i, b in enumerate(BRANDS):
            for row in blind_pairs(res[b["key"]]["a_only"], res[b["key"]]["c_only"], N_PAIRS, seed=100 + i):
                pid = f"{b['key']}-{row['pair']}"
                key[pid] = row["a_is"]
                v1, v2 = row["venue_1"], row["venue_2"]
                pairs.append({"pair": pid, "brand": b["name"], "about": b["about"],
                              "venue_1": f"{v1['name']} ({v1['type']})", "venue_1_website": v1["website"],
                              "venue_2": f"{v2['name']} ({v2['type']})", "venue_2_website": v2["website"], "better_fit": ""})
        with PAIRS.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(pairs[0]) if pairs else ["pair"])
            w.writeheader()
            w.writerows(pairs)

        demo = await pool.fetchval("select r.id from runs r join workspaces w on w.id = r.workspace_id "
                                   "where w.kind = 'demo' and r.status = 'done' order by r.created_at desc limit 1")
        reasons = await pool.fetch("select v.name, vs.reason, v.website from venue_scores vs join venues v on v.id = vs.venue_id "
                                   "where vs.run_id = $1 order by vs.rank limit 10", demo) if demo else []
        spent = await pool.fetchrow(
            "select (select count(*) from qloo_calls where not cache_hit and created_at >= $1) qloo, "
            "(select count(*) from qloo_calls where cache_hit and created_at >= $1) qloo_cached, "
            "(select count(*) from llm_calls where created_at >= $1) llm, "
            "(select count(*) from external_calls where not cache_hit and created_at >= $1) external", t0)
        summary = {"brand_overlap_a": brand_a, "brand_overlap_c": brand_c, "c_pool": len(pool_c), "spent": dict(spent),
                   **{k: {m: v[m] for m in ("signal", "a_vs_b", "a_vs_b_rho", "a_vs_c", "a_vs_c_rho", "a_in_osm", "a_in_pool")}
                      for k, v in res.items()}}
        await pool.execute("insert into evaluations (run_id, method, results) values ($1, $2, $3)",
                           demo, METHOD, {"summary": summary, "key": key,
                                          "lists": {k: {s_: [x["id"] for x in v[s_]] for s_ in "ABC"} for k, v in res.items()}})
        text = report(res, brand_a, brand_c, len(pool_c), len(pairs), reasons, dict(spent))
        kept = re.search(r"## Does lift change the list\?.*?(?=\n## )", REPORT.read_text() if REPORT.exists() else "", re.S)
        if kept:  # written by scripts/lift_effect.py; keep it across reruns
            text = text.replace("## Where Qloo did not help", kept.group(0).rstrip() + "\n\n## Where Qloo did not help", 1)
        REPORT.write_text(text)
        print(f"wrote {REPORT.relative_to(ROOT)} and {PAIRS.relative_to(ROOT)}; live calls spent: {dict(spent)}")
    finally:
        await close_services(svc)
        await db.close_pool()


def report(res: dict[str, Any], brand_a: float, brand_c: float, c_pool: int, n_pairs: int, reasons: list, spent: dict) -> str:
    names = {b["key"]: b["name"] for b in BRANDS}
    k1, k2 = (b["key"] for b in BRANDS)
    out = [
        "# Evaluation results: does Qloo change and improve the venue list?",
        "",
        f"Generated by `apps/api/scripts/evaluate.py` on {datetime.now(UTC):%Y-%m-%d}. Method: `docs/15-evaluation.md`. "
        f"City: Brooklyn. Venue types: {', '.join(TYPES)}. Top {TOP} per setup.",
        "",
        "| Setup | How venues are ranked |",
        "|---|---|",
        "| A. Qloo on | The app: Qloo taste percentile for the brand's comparables; lift = taste minus the same venues' taste for "
        "mass-market brands (fit = 0.7·taste + 0.3·max(lift, 0)) |",
        "| B. Popularity only | Qloo's popularity baseline for the same city and types, no taste signal |",
        f"| C. No Qloo | {c_pool} OpenStreetMap cafés and bars (with a website or email, fixed hash sample), scored 0–100 by the LLM from name, type and website |",
        "",
        "Brands (fictional, represented by real comparables that Qloo resolved):",
        "",
    ]
    out += [f"- **{names[k]}**: {next(b['about'] for b in BRANDS if b['key'] == k)} Signal: {', '.join(res[k]['signal'])}." for k in res]
    out += [
        "",
        "## Metrics 1–2: does Qloo change the decision?",
        "",
        f"| Metric | {names[k1]} | {names[k2]} |",
        "|---|---|---|",
        f"| Jaccard A vs B (top {TOP}) | {res[k1]['a_vs_b']:.2f} | {res[k2]['a_vs_b']:.2f} |",
        f"| Spearman A vs B, shared venues | {fmt(res[k1]['a_vs_b_rho'])} | {fmt(res[k2]['a_vs_b_rho'])} |",
        f"| Jaccard A vs C | {res[k1]['a_vs_c']:.2f} | {res[k2]['a_vs_c']:.2f} |",
        f"| Spearman A vs C, shared venues | {fmt(res[k1]['a_vs_c_rho'])} | {fmt(res[k2]['a_vs_c_rho'])} |",
        f"| A's top {TOP} found in OSM at all | {res[k1]['a_in_osm']} | {res[k2]['a_in_osm']} |",
        f"| A's top {TOP} inside C's candidate pool | {res[k1]['a_in_pool']} | {res[k2]['a_in_pool']} |",
        "",
        f"Brand sensitivity (Jaccard of the two brands' top {TOP}): **A {brand_a:.2f}**, C {brand_c:.2f}.",
        "",
        f"- Target A vs C ≤ 0.40: {ok(max(res[k1]['a_vs_c'], res[k2]['a_vs_c']) <= 0.4)}.",
        f"- Target brand 1 vs brand 2 ≤ 0.50 (A): {ok(brand_a <= 0.5)}.",
        "",
        "Read the A vs C number with the pool rows: C can only pick venues in its OSM sample, so part of the low overlap "
        "comes from the candidate pools, not from judgement. The blind pairs below are the fairer quality test.",
        "",
    ]
    for k in res:
        out += [f"### Top {TOP}: {names[k]}", "", "| # | A. Qloo on (fit, lift, confidence) | B. Popularity only | C. No Qloo (LLM) |",
                "|---|---|---|---|"]
        for i in range(TOP):
            a = res[k]["A"][i] if i < len(res[k]["A"]) else None
            cells = [f"{a['name']} ({round(a['fit'] * 100)}, {round(a['lift'] * 100):+d}, {a['confidence']})" if a else ""]
            cells += [res[k][s][i]["name"] if i < len(res[k][s]) else "" for s in "BC"]
            out.append(f"| {i + 1} | " + " | ".join(cells) + " |")
        out.append("")
    weak = {k: [v["name"] for v in res[k]["A"] if v["lift"] <= 0 or v["confidence"] == "low"] for k in res}
    out += [
        "## Where Qloo did not help (automatic checks)",
        "",
        *[f"- {names[k]}: {len(weak[k])} of A's top {TOP} have no positive lift or low confidence"
          f"{': ' + ', '.join(weak[k]) if weak[k] else ''}." for k in res],
        *[f"- {names[k]}: A shares {round(res[k]['a_vs_b'] * 100)}% of its list with plain popularity (B)." for k in res],
        "- Qloo only ranks places it knows; a venue missing from Qloo can never appear in A however good a fit it is.",
        "",
        "## Metric 3: blind preference (pending a judge)",
        "",
        f"`docs/evaluation_pairs.csv` has {n_pairs} pairs: one venue only A picked against one only C picked, sides shuffled. "
        "For each row, write 1 or 2 in `better_fit` (which venue fits the brand better, judged from the venues' own websites "
        "and menus), then run `uv run python scripts/evaluate.py --score ../../docs/evaluation_pairs.csv`. "
        "Target: A preferred in at least 7 of 10 per brand.",
        "",
        "## Metric 4: reason quality (pending a manual check)",
        "",
        "Top 10 of the sample run. Mark each Qloo-derived reason against the venue's own website or menu.",
        "",
        "| Venue | Reason shown in the app | Website | Consistent? (yes / partly / no) |",
        "|---|---|---|---|",
        *[f"| {r['name']} | {(r['reason'] or '').replace('|', '/')} | {r['website'] or ''} |  |" for r in reasons],
        "",
        "Target: yes or partly for at least 8 of 10.",
        "",
        "## Limits",
        "",
        "One city, two brands, top 15 lists, a single judge, and no sales outcomes. This shows whether Qloo changes and "
        "plausibly improves targeting, not whether it increases sales.",
        "",
        f"Calls spent by this evaluation: {spent}.",
        "",
    ]
    return "\n".join(out)


async def score(path: Path) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    try:
        row = await pool.fetchrow("select id, results from evaluations where method = $1 order by created_at desc limit 1", METHOD)
        key = row["results"]["key"]
        with path.open() as f:
            answers = {r["pair"]: int(r["better_fit"]) for r in csv.DictReader(f) if r["better_fit"].strip() in ("1", "2")}
        lines = ["", "### Blind preference results", ""]
        for b in BRANDS:
            p = b["key"]
            ans = {int(k.split("-")[1]): v for k, v in answers.items() if k.startswith(p + "-")}
            kk = {int(k.split("-")[1]): v for k, v in key.items() if k.startswith(p + "-")}
            wins, judged = a_wins(ans, kk)
            lines.append(f"- {b['name']}: A preferred in {wins} of {judged} judged pairs (target ≥ 7 of 10).")
        await pool.execute("update evaluations set results = results || $2 where id = $1", row["id"], {"blind": lines[3:]})
        text = REPORT.read_text().replace("## Metric 4", "\n".join(lines) + "\n\n## Metric 4", 1)
        REPORT.write_text(text)
        print("\n".join(lines))
    finally:
        await db.close_pool()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", type=Path, help="filled pairs CSV; appends metric 3 to the report")
    ap.add_argument("--c-pool", type=int, default=150, help="OSM venues per type that setup C scores")
    args = ap.parse_args()
    asyncio.run(score(args.score) if args.score else evaluate(args.c_pool))
