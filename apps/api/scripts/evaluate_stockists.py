"""Stockist backtest (docs/15-evaluation.md, EVL-03..05): do Qloo-based rankings find a brand's real Brooklyn accounts
better than an LLM? Reads docs/eval/stockists.csv (scripts/fetch_stockists.py). Spends live Qloo and LLM calls; every
Qloo call is cached, so a re-run is free.

    uv run python scripts/evaluate_stockists.py --split dev     # debug and tune
    uv run python scripts/evaluate_stockists.py --split test    # once, with the frozen pipeline
    uv run python scripts/evaluate_stockists.py --split all     # report both (reads the cache)
"""

import argparse
import asyncio
import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fetch_stockists import BRANDS
from pydantic import BaseModel, Field

from tasteroute_api import db
from tasteroute_api.categories import pack_for
from tasteroute_api.evaluation import hash_order, long_tail, mean_percentile_rank, recall_at_k
from tasteroute_api.llm.prompts import load
from tasteroute_api.llm.structured import structured
from tasteroute_api.main import build_services, close_services
from tasteroute_api.qloo import api
from tasteroute_api.qloo.client import Trace
from tasteroute_api.qloo.guards import guard_places
from tasteroute_api.scoring import names, rank
from tasteroute_api.services.drafts import short_name
from tasteroute_api.services.resolve import best_match
from tasteroute_api.settings import get_settings

ROOT = Path(__file__).resolve().parents[3]
CSV, POOLS, LLM_CACHE = ROOT / "docs/eval/stockists.csv", ROOT / "docs/eval/pools", ROOT / "docs/eval/llm"
REPORT, WEB = ROOT / "docs/evaluation-stockists.md", ROOT / "apps/web/public/evaluation.json"
CITY = {"query": "Brooklyn", "lat": 40.6526, "lon": -73.9497, "bbox": [40.5503390, -74.0566880, 40.7394340, -73.8329450]}
PAGES, BATCH, POP_TOP = 10, 50, 50
METHODS = ["Q-fit", "Q-raw", "POP", "LLM", "Q-fit+LLM"]


class Score(BaseModel):
    id: str
    score: int = Field(ge=0, le=100)


class Scores(BaseModel):
    scores: list[Score]


def venue(p: dict[str, Any], vt: str) -> dict[str, Any]:
    """One pool row from an insights Place or a /search place (tags as `id` or `tag_id`)."""
    props = p.get("properties") or {}
    loc = p.get("location") or {}
    return {"id": p["entity_id"], "name": p["name"], "type": vt, "neighborhood": props.get("neighborhood") or "",
            "address": props.get("address") or "", "lat": loc.get("lat"), "lon": loc.get("lon"),
            "popularity": p.get("popularity") or 0.0,
            "tags": [t.get("id") or t.get("tag_id") for t in p.get("tags") or []]}


def street_no(address: str) -> str | None:
    m = re.match(r"\s*(\d+)", address or "")
    return m.group(1) if m else None


def same_place(name: str, address: str, v: dict[str, Any]) -> bool:
    if not (names.is_match(name, v["name"]) or names.is_match(name, short_name(v["name"]))):
        return False
    a, b = street_no(address), street_no(v["address"])
    return a is None or b is None or a == b


async def comparables(svc: Any, pack: Any, b: dict[str, Any], trace: Trace) -> list[tuple[str, str]]:
    """The pre-registered comparables in order, then backups, until at least 3 resolve."""
    out: list[tuple[str, str]] = []
    for i, n in enumerate(b["comparables"] + b["backups"]):
        if i >= len(b["comparables"]) and len(out) >= 3:
            break
        found, _ = await api.search(svc.qloo, n, pack.product_entity_types, trace)
        m = best_match(n, found)
        if m:
            out.append((m[0].entity_id, m[0].name))
    return out


async def build_pool(svc: Any, pack: Any, b: dict[str, Any], trace: Trace) -> dict[str, dict[str, Any]]:
    """Per venue type, Qloo's PAGES × 50 best-known Brooklyn venues (popularity order, no signal). Accounts count only if
    they are in it, so accounts and non-accounts are picked the same way (see the dev-run note in docs/15-evaluation.md)."""
    pool: dict[str, dict[str, Any]] = {}
    for vt in b["types"]:
        tags = pack.venue_type(vt).qloo_tags
        for page in range(1, PAGES + 1):
            body, _, _ = await api.place_insights(svc.qloo, city_query=CITY["query"], tags=tags, page=page, trace=trace)
            for p in guard_places(body.results.entities, required_tags=tags, bbox=CITY["bbox"]).kept:
                pool.setdefault(p.entity_id, venue(p.model_dump(), vt))
    return pool


def resolve(rows: list[dict[str, str]], pool: dict[str, dict[str, Any]]) -> tuple[set[str], dict[str, int], list[dict[str, Any]]]:
    """Accounts to pool venues: the app's name match and the same street number when both have one."""
    truth: set[str] = set()
    log = []
    for r in rows:
        name, addr = r["stockist_name"], r["stockist_address"]
        hit = next((v for v in pool.values() if same_place(name, addr, v)), None)
        if hit:
            truth.add(hit["id"])
        log.append({"name": name, "address": addr, "qloo": hit["name"] if hit else ""})
    return truth, {"accounts": len(rows), "in_pool": sum(bool(x["qloo"]) for x in log)}, log


async def affinities(svc: Any, ids: list[str], signal: list[str], trace: Trace, explain: bool = False
                     ) -> tuple[dict[str, float], dict[str, list[tuple[str, float]]]]:
    aff: dict[str, float] = {}
    drivers: dict[str, list[tuple[str, float]]] = {}
    for i in range(0, len(ids), BATCH):
        body, _, _ = await api.place_insights(svc.qloo, results_ids=ids[i:i + BATCH], signal_ids=signal, explain=explain,
                                              trace=trace)
        for p in body.results.entities:
            if p.affinity is not None:
                aff[p.entity_id] = p.affinity
                drivers[p.entity_id] = [(x.entity_id, x.score) for x in p.explain()]
    return aff, drivers


async def llm_scores(svc: Any, b: dict[str, Any], comps: list[str], pool: list[dict[str, Any]]) -> dict[str, int]:
    """Cached in docs/eval/llm/<brand>.json per prompt version and pool, so a re-run (and anyone checking) gets the same
    scores without new LLM calls."""
    system, version = load("eval_rank_stockists")
    order = hash_order([v["id"] for v in pool], b["key"])
    cache = LLM_CACHE / f"{b['key']}.json"
    if cache.exists():
        c = json.loads(cache.read_text())
        if c["version"] == version and sorted(c["scores"]) == sorted(order):
            return {k: int(v) for k, v in c["scores"].items()}
    by_id = {v["id"]: v for v in pool}
    got: dict[str, int] = {}
    for start in range(0, len(order), BATCH):
        batch = [by_id[i] for i in order[start:start + BATCH]]
        lines = "\n".join(f"v{j}: {v['name']} ({v['type']}{', ' + v['neighborhood'] if v['neighborhood'] else ''})"
                          for j, v in enumerate(batch))
        user = (f"Products: {b['description']}\nBrands with a similar following: {', '.join(comps)}\n"
                f"City: Brooklyn, New York\n\nVenues:\n{lines}")
        out = await structured(svc.llm, Scores, system, user, purpose="evaluation", prompt_version=version,
                               temperature=0.0, max_tokens=3000)
        s = {x.id: x.score for x in out.scores}
        got |= {v["id"]: s.get(f"v{j}", -1) for j, v in enumerate(batch)}
    LLM_CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"version": version, "scores": got}, indent=0) + "\n")
    return got


def rankings(b: dict[str, Any], pool: dict[str, dict[str, Any]], target: dict[str, float], generic: dict[str, float],
             llm: dict[str, int]) -> tuple[dict[str, list[str]], dict[str, rank.Scored]]:
    tie = {v: i for i, v in enumerate(hash_order(list(pool), b["key"]))}
    per_type = []
    for vt in b["types"]:
        cands = [rank.Candidate(i, target.get(i, 0.0), v["popularity"]) for i, v in pool.items() if v["type"] == vt]
        per_type.append(rank.score_against_generic(vt, cands, generic))
    fit = {s.venue_id: s for s in rank.merge(per_type, 100_000)}
    out = {
        "Q-fit": sorted(pool, key=lambda i: (-fit[i].fit, -fit[i].target_pct, tie[i])),
        "Q-raw": sorted(pool, key=lambda i: (-target.get(i, -1.0), tie[i])),
        "POP": sorted(pool, key=lambda i: (-pool[i]["popularity"], tie[i])),
        "LLM": sorted(pool, key=lambda i: (-llm.get(i, -1), tie[i])),
    }
    # Exploratory, not TasteRoute's ranking (added after the dev run): the mean of the Q-fit and LLM positions.
    pos = {k: {v: r for r, v in enumerate(out[k])} for k in ("Q-fit", "LLM")}
    out["Q-fit+LLM"] = sorted(pool, key=lambda i: (pos["Q-fit"][i] + pos["LLM"][i], tie[i]))
    return out, fit


def metrics(order: dict[str, list[str]], truth: set[str], n: int) -> dict[str, Any]:
    tail = long_tail(truth, order["POP"][:POP_TOP])
    m: dict[str, Any] = {k: {"recall15": recall_at_k(v, truth, 15), "recall30": recall_at_k(v, truth, 30),
                             "found30": len(set(v[:30]) & truth), "mpr": mean_percentile_rank(v, truth),
                             "tail30": recall_at_k(v, tail, 30)} for k, v in order.items()}
    m["RANDOM"] = {"recall15": round(15 / n, 3), "recall30": round(30 / n, 3), "found30": round(30 * len(truth) / n, 1),
                   "mpr": 50.0, "tail30": round(30 / n, 3)}
    return m | {"truth": len(truth), "tail": len(tail), "pool": n}


async def run_brand(svc: Any, pack: Any, b: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    trace = Trace(step="evaluate_stockists")
    comps = await comparables(svc, pack, b, trace)
    signal = [i for i, _ in comps]
    if len(comps) < 3:  # pre-registered: at least 3 comparables must resolve, or the brand is not scored
        return {"brand": b["brand"], "key": b["key"], "split": b["split"], "description": b["description"],
                "types": b["types"], "comparables": [n for _, n in comps], "counts": {"accounts": len(rows)},
                "not_scored": f"{len(comps)} of {len(b['comparables'] + b['backups'])} comparables "
                              f"({', '.join(b['comparables'] + b['backups'])}) are known to Qloo; the minimum is 3"}
    pool = await build_pool(svc, pack, b, trace)
    truth, counts, log = resolve(rows, pool)
    ids = sorted(pool)
    target, drivers = await affinities(svc, ids, signal, trace, explain=True)
    generic, _ = await affinities(svc, ids, pack.baseline_entities, trace)
    llm = await llm_scores(svc, b, [n for _, n in comps], list(pool.values()))
    order, fit = rankings(b, pool, target, generic, llm)
    POOLS.mkdir(parents=True, exist_ok=True)
    (POOLS / f"{b['key']}.json").write_text(json.dumps(
        [{"id": i, "name": pool[i]["name"], "type": pool[i]["type"], "neighborhood": pool[i]["neighborhood"],
          "stockist": i in truth} for i in ids], indent=1, ensure_ascii=False) + "\n")
    pos = {k: {v: r + 1 for r, v in enumerate(o)} for k, o in order.items()}
    comp_names = dict(comps)
    stockists = sorted(
        ({"name": pool[i]["name"], "type": pool[i]["type"], "neighborhood": pool[i]["neighborhood"],
          **{k: pos[k][i] for k in METHODS}, "taste_pct": fit[i].target_pct, "mass_pct": fit[i].baseline_pct,
          "drivers": [comp_names.get(e, e) for e, _ in sorted(drivers.get(i, []), key=lambda x: -x[1])[:2]]}
         for i in truth), key=lambda x: x["Q-fit"])
    return {"brand": b["brand"], "key": b["key"], "split": b["split"], "description": b["description"],
            "types": b["types"], "comparables": [n for _, n in comps], "counts": counts,
            "metrics": metrics(order, truth, len(pool)), "stockists": stockists, "resolution": log,
            "top10": {k: [pool[i]["name"] for i in order[k][:10]] for k in METHODS}}


LESSONS = """## Where Qloo lost and why

Written after the test run; every number is in the tables above or in `docs/eval/results-all.json`.

- **Qloo doesn't know the natural-wine world (Steven Graf Wine).** None of six well-known natural-wine producers and \
importers resolve in Qloo `/search`, so there is no taste signal. The app fails closed in that case (step 3 says Qloo \
doesn't know the brands), and the pre-registered rule did the same here. The script only enforced that rule after the \
first test run, which had ranked this brand with no signal (recall@30 Q-fit 0%, LLM 20%; kept in \
`docs/eval/results-test.json`).
- **The mass-market baseline works against coffee (Parlor Coffee).** The two café accounts, Odd Fox Coffee and Petee's \
Café, sit at Qloo taste percentiles 96 and 90 but also at mass-market percentiles 87 and 83, because the mass-market \
brands include Starbucks and Dunkin'. Lift pushes them down and Q-fit's top 10 turns into restaurants and hotels. Q-raw's \
top 10 is specialty cafés (SEY, Blue Bottle, Black Brick) and finds 1 of the 4 accounts, as the LLM does. Only 4 of 47 \
accounts are among Qloo's best-known venues, so this brand says little either way.
- **Lift did not help on this test.** Q-raw matched or beat Q-fit on recall@30 for every scored test brand (Parlor 25% vs \
0%, St. Agrestis 22% vs 19%, Casamara Club 14% vs 14%).
- **The LLM reads names and knows famous venues.** Its mean percentile rank beats Q-fit on all three scored test brands \
(86 vs 78, 73 vs 66, 70 vs 69) and both dev brands. Its top picks carry the category in the name ("Coffee Project", \
"The Whiskey Annex", "Black Mountain Wine House") or are famous (Lilia, The Four Horsemen).
- **Where Qloo was ahead: the top of the list for taste-led brands.** St. Agrestis recall@15: Q-raw 19% (7 of 36), Q-fit \
11%, LLM 11%. Accounts Qloo ranks high and the LLM does not: Grand Army (Q-fit 9th, LLM 284th), June (2nd vs 101st), \
Madeline's (22nd vs 283rd), all driven by fans of Ghia and Campari. For Casamara Club the LLM has no account in its \
top 30; Q-fit has Glasserie at 10th.

**What it means.** On these brands Qloo's taste signal finds about as many real accounts as an LLM that reads venue \
names: 8 of 47 in the top 30 for Q-fit, 8 for the LLM, 10 for Q-raw, about 1.5 by chance. They find different ones \
(Grand Army and June for Qloo, Lilia and Cecconi's for the LLM), so the app shows both (the LLM column on the results \
page) instead of claiming Qloo wins. The mass-market set should not contain the brand's own category (no coffee chains \
for a coffee brand); that change needs new brands to test it on, so it is logged, not made."""


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def report(res: list[dict[str, Any]], spent: dict[str, Any]) -> str:
    skipped = [r for r in res if r.get("not_scored")]
    res = [r for r in res if not r.get("not_scored")]
    test = [r for r in res if r["split"] == "test"]
    wins = sum(r["metrics"]["Q-fit"]["recall30"] > r["metrics"]["LLM"]["recall30"] for r in test)
    ties = sum(r["metrics"]["Q-fit"]["recall30"] == r["metrics"]["LLM"]["recall30"] for r in test)
    out = [
        "# Stockist backtest: does TasteRoute find a brand's real accounts?",
        "",
        f"Generated by `apps/api/scripts/evaluate_stockists.py` on {datetime.now(UTC):%Y-%m-%d}. Method pre-registered in "
        "`docs/15-evaluation.md` (\"Stockist backtest\") before any test brand was run. Ground truth: "
        "`docs/eval/stockists.csv`; pools: `docs/eval/pools/`.",
        "",
        "Each brand's Brooklyn accounts come from the brand's own public account list. Every method ranks the same pool: "
        f"Qloo's {PAGES * 50} best-known Brooklyn venues of each of the brand's venue types (popularity order, no taste "
        "signal). An account counts when it is in the pool, so accounts and other venues are picked the same way. "
        "No method sees the brand's name.",
        "",
        "| Method | How it ranks the pool |",
        "|---|---|",
        "| **Q-fit** (TasteRoute) | The app's fit: Qloo taste for the comparables vs mass-market taste at the same venues |",
        "| Q-raw | Qloo affinity for the comparables only |",
        "| POP | Qloo popularity only |",
        "| LLM | Gemma 4 31B from the description, the comparables and each venue's name, type and neighbourhood |",
        "| Q-fit+LLM | Exploratory (added after the dev run, before the test run): the mean of the Q-fit and LLM positions |",
        "| RANDOM | Expected value |",
        "",
    ]
    if test:
        out += [f"**Result: Q-fit beat the LLM on recall@30 in {wins} of {len(test)} scored test brands"
                + (f" ({ties} tied)" if ties else "") + f". Target was 3 of 4: {'met' if wins >= 3 else 'missed'}.**", ""]
    out += [f"Not scored: **{r['brand']}** ({r['split']}): {r['not_scored']}." for r in skipped]
    out += [""] if skipped else []
    out += ["## Recall@30 by brand", "",
            "| Brand | Split | Accounts in the pool | Pool | " + " | ".join(METHODS) + " | RANDOM |",
            "|---|---|---|---|" + "---|" * (len(METHODS) + 1)]
    for r in res:
        m, c = r["metrics"], r["counts"]
        cells = [f"{pct(m[k]['recall30'])} ({m[k]['found30']})" for k in METHODS]
        out.append(f"| {r['brand']} | {r['split']} | {m['truth']} of {c['accounts']} | {m['pool']} | " + " | ".join(cells)
                   + f" | {pct(m['RANDOM']['recall30'])} |")
    out += ["", "Cells: recall@30 (accounts found in the top 30).", ""]
    for r in res:
        m, c = r["metrics"], r["counts"]
        out += [f"## {r['brand']} ({r['split']})", "",
                f"{r['description']}. Venue types: {', '.join(r['types'])}. Comparables: {', '.join(r['comparables'])}.", "",
                f"Accounts: {c['accounts']} in Brooklyn; {c['in_pool']} are among Qloo's {PAGES * 50} best-known venues of "
                f"each type (the pool); the rest are excluded for every method. "
                f"Long tail (outside POP's top {POP_TOP}): {m['tail']} of {m['truth']}.", "",
                "| Metric | " + " | ".join([*METHODS, "RANDOM"]) + " |", "|---|" + "---|" * (len(METHODS) + 1)]
        for key, label, f in (("recall15", "recall@15", pct), ("recall30", "recall@30", pct),
                              ("mpr", "mean percentile rank", lambda x: "n/a" if x is None else f"{x:.0f}"),
                              ("tail30", "long-tail recall@30", pct)):
            out.append(f"| {label} | " + " | ".join(f(m[k][key]) for k in [*METHODS, "RANDOM"]) + " |")
        out += ["", "| Account | Type | Q-fit rank | LLM rank | POP rank | Taste pct | Mass-market pct | Qloo drivers |",
                "|---|---|---|---|---|---|---|---|"]
        out += [f"| {s['name']} | {s['type']} | {s['Q-fit']} | {s['LLM']} | {s['POP']} | {s['taste_pct'] * 100:.0f} | "
                f"{s['mass_pct'] * 100:.0f} | {', '.join(s['drivers'])} |" for s in r["stockists"]]
        out.append("")
    out += [LESSONS, "",
            "## Limits", "",
            "- One city and six brands; the four test brands decide the claim. Small samples: one account moves recall@30 "
            "by several points.",
            "- Account lists are what each brand publishes; some are out of date, and shops drop out at resolution.",
            f"- Accounts outside Qloo's {PAGES * 50} best-known venues per type are excluded for every method, so the test "
            "says nothing about the least-known venues.",
            "- A venue Qloo returns no taste reading for counts as the lowest taste score.",
            "- The LLM scores the pool in batches of 50, so its scores are only compared within the pool order it was given "
            "(fixed hash).", "",
            "## Calls spent", "", f"Qloo live {spent['qloo']} (cached {spent['qloo_cached']}), LLM {spent['llm']}.", ""]
    return "\n".join(out)


def web_summary(res: list[dict[str, Any]]) -> dict[str, Any]:
    """apps/web/public/evaluation.json for the /evaluation page: totals, per-brand rows, one featured account."""
    scored = [r for r in res if not r.get("not_scored")]
    test = [r for r in scored if r["split"] == "test"]
    found = {k: sum(r["metrics"][k]["found30"] for r in test) for k in [*METHODS, "RANDOM"]}
    # An account in Q-fit's top 30 that the LLM ranked lowest.
    feat_brand, feat = max(((r, s) for r in test for s in r["stockists"] if s["Q-fit"] <= 30), key=lambda rs: rs[1]["LLM"])
    return {
        "generated": datetime.now(UTC).date().isoformat(),
        "city": "Brooklyn",
        "test_brands_scored": len(test),
        "accounts": sum(r["metrics"]["truth"] for r in test),
        "found_top30": {k: round(v, 1) for k, v in found.items()},
        "wins": {"q_fit": sum(r["metrics"]["Q-fit"]["recall30"] > r["metrics"]["LLM"]["recall30"] for r in test),
                 "llm": sum(r["metrics"]["Q-fit"]["recall30"] < r["metrics"]["LLM"]["recall30"] for r in test),
                 "ties": sum(r["metrics"]["Q-fit"]["recall30"] == r["metrics"]["LLM"]["recall30"] for r in test)},
        "target": "TasteRoute beats the LLM on recall@30 in 3 of 4 test brands",
        "target_met": False,
        "brands": [{"brand": r["brand"], "split": r["split"], "what": r["description"], "comparables": r["comparables"],
                    **({"not_scored": r["not_scored"]} if r.get("not_scored") else {
                        "accounts": r["metrics"]["truth"], "pool": r["metrics"]["pool"],
                        "recall30": {k: r["metrics"][k]["recall30"] for k in [*METHODS, "RANDOM"]},
                        "mpr": {k: r["metrics"][k]["mpr"] for k in [*METHODS, "RANDOM"]}})} for r in res],
        "featured": {"brand": feat_brand["brand"], "what": feat_brand["description"], "venue": feat["name"],
                     "type": feat["type"], "neighborhood": feat["neighborhood"], "q_fit_rank": feat["Q-fit"],
                     "llm_rank": feat["LLM"], "pool": feat_brand["metrics"]["pool"], "drivers": feat["drivers"]},
        "doc": "https://github.com/divyanshu-patil/TasteRoute/blob/main/docs/evaluation-stockists.md",
    }


async def main(split: str) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    svc = build_services(s, pool)
    try:
        t0 = await pool.fetchval("select now()")
        pack = pack_for("food_drink")
        rows = list(csv.DictReader(CSV.open()))
        res = []
        for b in BRANDS:
            if split != "all" and b["split"] != split:
                continue
            r = await run_brand(svc, pack, b, [x for x in rows if x["brand"] == b["brand"]])
            res.append(r)
            if r.get("not_scored"):
                print(f"{b['brand']}: not scored, {r['not_scored']}")
                continue
            m = r["metrics"]
            print(f"{b['brand']}: truth {m['truth']}/{r['counts']['accounts']}, pool {m['pool']}, recall@30 "
                  + ", ".join(f"{k} {pct(m[k]['recall30'])}" for k in [*METHODS, "RANDOM"]))
        spent = await pool.fetchrow(
            "select (select count(*) from qloo_calls where not cache_hit and created_at >= $1) qloo, "
            "(select count(*) from qloo_calls where cache_hit and created_at >= $1) qloo_cached, "
            "(select count(*) from llm_calls where created_at >= $1) llm", t0)
        out = ROOT / f"docs/eval/results-{split}.json"
        out.write_text(json.dumps({"generated": datetime.now(UTC).isoformat(), "spent": dict(spent), "brands": res},
                                  indent=1, ensure_ascii=False) + "\n")
        if split == "all":
            REPORT.write_text(report(res, dict(spent)))
            WEB.write_text(json.dumps(web_summary(res), indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {out.relative_to(ROOT)}; live calls spent: {dict(spent)}")
    finally:
        await close_services(svc)
        await db.close_pool()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test", "all"], required=True)
    asyncio.run(main(ap.parse_args().split))
