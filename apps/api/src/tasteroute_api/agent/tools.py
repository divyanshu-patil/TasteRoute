"""Agent tools. Deterministic over Qloo responses: the LLM only decides when to call them (AGT-06)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from ..errors import AppError, QlooError
from ..qloo import api
from ..qloo.client import stored_response
from ..qloo.compact import tag_kind
from ..qloo.guards import guard_places
from ..qloo.models import InsightsBody, Place
from ..scoring import SCORING_VERSION, buyability, rank
from ..scoring.fit import FitThresholds, best_product, zscores
from ..scoring.reasons import distinctive, plain_tags, reason
from .context import RunContext

FATAL_QLOO = {"qloo_auth", "qloo_unconfigured", "qloo_budget_exceeded"}
MAX_SIGNAL = 15


class NoEntities(AppError):
    code, status, title = "no_entities_resolved", 422, "Qloo doesn't know these products or similar brands yet"


class NoVenues(AppError):
    code, status, title = "no_venues", 422, "Qloo returned no venues for these types in this city"


async def _signal(ctx: RunContext) -> list[dict[str, Any]]:
    rows = await ctx.pool.fetch(
        "select distinct on (qloo_entity_id) qloo_entity_id, name, product_id from product_entities "
        "where run_id = $1 order by qloo_entity_id, created_at",
        ctx.rid,
    )
    return [dict(r) for r in rows][:MAX_SIGNAL]


# ---------------------------------------------------------------- resolve_entities (F02)
async def resolve_entities(ctx: RunContext, product_ids: list[str] | None = None) -> dict[str, Any]:
    from ..services.resolve import resolve_product

    pids = product_ids or list(ctx.products)
    chosen_by_product: dict[str, list[str]] = ctx.settings_json.get("entity_ids_by_product") or {}
    await ctx.pool.execute("delete from product_entities where run_id = $1", ctx.rid)
    resolution: dict[str, Any] = {}
    for pid in pids:
        p = ctx.products[pid]
        if p.get("entities") is not None:  # confirmed in the wizard (possibly emptied by the user)
            res = {"status": "resolved", "entities": p["entities"], "dropped": [], "message": "Confirmed by you"}
        else:
            res = await resolve_product(ctx.svc, ctx.brand, p, ctx.pack, ctx.trace("resolve_entities"), ctx.run_id)
        ents = res["entities"]
        if chosen_by_product.get(pid):
            ents = [e for e in ents if e["entity_id"] in chosen_by_product[pid]]
        for e in ents:
            await ctx.pool.execute(
                "insert into product_entities (run_id, product_id, qloo_entity_id, name, entity_type, role, similarity, "
                "source_call_id) values ($1,$2,$3,$4,$5,$6,$7,$8) on conflict do nothing",
                ctx.rid, p["id"], e["entity_id"], e["name"], e.get("type") or "urn:entity:brand", e["role"],
                e.get("similarity"), _uuid(e.get("source_call_id")),
            )
        resolution[pid] = {"status": "resolved" if ents else "unresolved", "message": res["message"],
                           "dropped": res["dropped"], "entities": [e["name"] for e in ents]}
        if not ents:
            await ctx.warn("product_unresolved", f"{p['name']}: {res['message']}")
    ctx.settings_json["resolution"] = resolution
    await ctx.save_settings()
    resolved = [pid for pid, r in resolution.items() if r["entities"]]
    if not resolved:
        raise NoEntities()
    return {
        "resolved_products": len(resolved),
        "unresolved_products": [ctx.products[p]["name"] for p in resolution if p not in resolved],
        "entities": sorted({n for r in resolution.values() for n in r["entities"]}),
    }


def _uuid(v: Any) -> Any:
    import uuid

    try:
        return uuid.UUID(str(v)) if v else None
    except ValueError:
        return None


# ---------------------------------------------------------------- rank_venues (F03)
async def rank_venues(ctx: RunContext, venue_types: list[str] | None = None, max_venues: int | None = None) -> dict[str, Any]:
    types = venue_types or ctx.venue_types
    signal = await _signal(ctx)
    if not signal:
        raise NoEntities()
    city_q = ctx.city.get("qloo_query") or ctx.city["name"]
    trace = ctx.trace("rank_venues")

    generic = ctx.pack.baseline_entities if ctx.pack.baseline_signal == "fixed_entities" else []

    async def one(vt: str) -> tuple[str, dict[str, str]]:
        vtype = ctx.pack.venue_type(vt)
        assert vtype is not None
        ids = [s["qloo_entity_id"] for s in signal]
        if generic:  # the same venues under mass-market brands (D-23): same number of calls, the second needs the first
            body, tcall, _ = await api.place_insights(ctx.svc.qloo, city_query=city_q, tags=vtype.qloo_tags, signal_ids=ids,
                                                      explain=True, trace=trace)
            venues = [p.entity_id for p in body.results.entities]
            _, gcall, _ = await api.place_insights(ctx.svc.qloo, results_ids=venues, signal_ids=generic, trace=trace)
            return vt, {"target": tcall, "generic": gcall}
        (_, tcall, _), (_, bcall, _) = await asyncio.gather(
            api.place_insights(ctx.svc.qloo, city_query=city_q, tags=vtype.qloo_tags, signal_ids=ids, explain=True, trace=trace),
            api.place_insights(ctx.svc.qloo, city_query=city_q, tags=vtype.qloo_tags, trace=trace),
        )
        return vt, {"target": tcall, "baseline": bcall}

    calls = await asyncio.gather(*[one(vt) for vt in types])
    ctx.settings_json["calls"] = dict(calls)
    ctx.settings_json["signal"] = [{"entity_id": s["qloo_entity_id"], "name": s["name"]} for s in signal]
    ctx.settings_json.setdefault("weights", {"target": rank.Weights().target, "lift": rank.Weights().lift})
    ctx.settings_json["scoring_version"] = SCORING_VERSION
    await ctx.save_settings()
    summary = await score_from_stored(ctx, max_venues=max_venues)
    return summary


def _products_text(ctx: RunContext, pid: str | None = None) -> str:
    ps = [ctx.products[pid]] if pid else list(ctx.products.values())
    return " ".join(str(p.get(k) or "") for p in ps for k in ("name", "kind", "notes"))


def _buyability_flags(ctx: RunContext, per_type: list[list[rank.Scored]], places: dict[str, Place]) -> str:
    """Adds chain, signal_brand_venue and maker_competitor flags (RNK-09); returns the warning naming what is hidden."""
    b = ctx.pack.buyability
    chain = buyability.chains({vid: p.name for vid, p in places.items()}, b.chains)
    signal = [s["name"] for s in ctx.settings_json.get("signal") or []]
    makers = [(m.kinds, m.tags) for m in b.makers]
    text = _products_text(ctx)
    for rows in per_type:
        for s in rows:
            p = places[s.venue_id]
            s.flags += [f for f, on in (
                ("chain", s.venue_id in chain),
                ("signal_brand_venue", buyability.own_brand(p.name, signal)),
                ("maker_competitor", buyability.maker({t.id for t in p.tags}, text, makers)),
                ("rising", (p.audience_growth or 0) > 0),  # RNK-10: display only, fit never uses it
            ) if on and f not in s.flags]
    n = {f: len({s.venue_id for rows in per_type for s in rows if f in s.flags}) for f in buyability.HIDDEN}
    if not any(n.values()):
        return ""
    names = sorted({places[s.venue_id].name for rows in per_type for s in rows if set(s.flags) & set(buyability.HIDDEN)})
    return (f"Hidden by default, listed after the rest: {n['chain']} chain venues and {n['signal_brand_venue']} venues of "
            f"brands you resemble ({', '.join(names[:8])}{'…' if len(names) > 8 else ''}).")


async def load_places(ctx: RunContext, call_id: str) -> InsightsBody:
    return InsightsBody.model_validate(await stored_response(ctx.pool, call_id) or {})


async def score_from_stored(ctx: RunContext, *, max_venues: int | None = None, emit_warnings: bool = True) -> dict[str, Any]:
    """Score from stored target/baseline responses. Used by rank_venues and by /rescore (no new calls)."""
    w = ctx.settings_json.get("weights") or {}
    weights = rank.Weights(target=float(w.get("target", 0.7)), lift=float(w.get("lift", 0.3)))
    cap = min(max_venues or ctx.svc.settings.max_venues_per_run, ctx.svc.settings.max_venues_per_run)
    per_type: list[list[rank.Scored]] = []
    places: dict[str, Place] = {}
    by_type: dict[str, int] = {}
    baseline_counts: dict[str, int] = {}
    warnings: list[tuple[str, str]] = []
    for vt, c in ctx.settings_json["calls"].items():
        vtype = ctx.pack.venue_type(vt)
        tags = vtype.qloo_tags if vtype else None
        target = await load_places(ctx, c["target"])
        gt = guard_places(target.results.entities, required_tags=tags, bbox=ctx.city.get("bbox"))
        warnings += [("guard_drops", f"{vt}: {m}") for m in gt.warnings]
        if not gt.kept:
            warnings.append(("type_empty", f"No {vt} venues found; skipped."))
            continue
        cands = [
            rank.Candidate(p.entity_id, p.affinity, p.popularity, rank.support([(x.entity_id, x.score) for x in p.explain()]))
            for p in gt.kept
        ]
        signals = len(ctx.settings_json.get("signal") or []) or 2
        if "generic" in c:
            aff = {p.entity_id: p.affinity for p in (await load_places(ctx, c["generic"])).results.entities
                   if p.affinity is not None}
            scored = rank.score_against_generic(vt, cands, aff, weights, signals=signals)
            missing = sum("generic_missing" in s.flags for s in scored)
            if missing > 0.2 * len(scored):
                warnings.append(("baseline_partial", f"{vt}: Qloo gave no mass-market reading for {missing} of {len(scored)} "
                                                     "venues; they count as the lowest."))
        else:  # scored before D-23: popularity baseline
            gb = guard_places((await load_places(ctx, c["baseline"])).results.entities, required_tags=tags,
                              bbox=ctx.city.get("bbox"))
            warnings += [("guard_drops", f"{vt}: {m}") for m in gb.warnings]
            scored = rank.score_type(vt, cands, [p.entity_id for p in gb.kept], {p.entity_id: p.popularity for p in gb.kept},
                                     weights, signals=signals)
            baseline_counts[vt] = len(gb.kept)
        per_type.append(scored)
        by_type[vt] = len(scored)
        for p in gt.kept:
            places.setdefault(p.entity_id, p)
    hidden = _buyability_flags(ctx, per_type, places)
    if hidden:
        warnings.append(("hidden_venues", hidden))
    merged = rank.merge(per_type, cap, buyability.HIDDEN)
    if not merged:
        raise NoVenues()
    warnings += [("low_coverage", m) for m in rank.coverage_warnings(len(merged), baseline_counts)]

    async with ctx.pool.acquire() as con, con.transaction():
        await con.execute("delete from venue_scores where run_id = $1", ctx.rid)
        for s in merged:
            p = places[s.venue_id]
            loc = p.location
            vid = await con.fetchval(
                "insert into venues (qloo_entity_id, name, lat, lon, address, tags, properties, website, updated_at) "
                "values ($1,$2,$3,$4,$5,$6,$7,$8, now()) on conflict (qloo_entity_id) do update set name = excluded.name, "
                "lat = excluded.lat, lon = excluded.lon, address = excluded.address, tags = excluded.tags, "
                "properties = excluded.properties, website = coalesce(excluded.website, venues.website), updated_at = now() "
                "returning id",
                p.entity_id, p.name, loc.lat if loc else None, loc.lon if loc else None, p.properties.get("address"),
                [t.model_dump() for t in p.tags], p.properties, p.properties.get("website"),
            )
            await con.execute(
                "insert into venue_scores (run_id, venue_id, venue_type, target_pct, baseline_pct, lift, fit, confidence, "
                "flags, rank, popularity_pct) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                ctx.rid, vid, s.venue_type, s.target_pct, s.baseline_pct, s.lift, s.fit, s.confidence, s.flags, s.rank,
                s.popularity_pct,
            )
    ctx.settings_json["by_type"] = by_type
    await ctx.save_settings()
    if emit_warnings:
        for code, msg in warnings:
            await ctx.warn(code, msg)
    return {
        "ranked": len(merged),
        "by_type": by_type,
        "top": [places[s.venue_id].name for s in merged[:5]],
        "high_confidence": sum(1 for s in merged if s.confidence == "high"),
        "warnings": [m for _, m in warnings][:5],
    }


async def _ranked(ctx: RunContext) -> list[dict[str, Any]]:
    rows = await ctx.pool.fetch(
        "select vs.*, v.qloo_entity_id, v.name, v.tags from venue_scores vs join venues v on v.id = vs.venue_id "
        "where vs.run_id = $1 order by vs.rank",
        ctx.rid,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- match_products (F04)
async def match_products(ctx: RunContext) -> dict[str, Any]:
    ranked = await _ranked(ctx)
    if not ranked:
        raise NoVenues()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ranked:
        groups[r["venue_type"]].append(r)
    ents = await ctx.pool.fetch("select product_id, qloo_entity_id from product_entities where run_id = $1", ctx.rid)
    by_product: dict[str, list[str]] = defaultdict(list)
    for e in ents:
        by_product[str(e["product_id"])].append(e["qloo_entity_id"])

    pct: dict[str, dict[str, float]] = defaultdict(dict)  # venue_id -> product_id -> percentile
    z: dict[str, dict[str, float]] = defaultdict(dict)  # venue_id -> product_id -> standardised affinity
    raw: dict[str, dict[str, float]] = defaultdict(dict)  # venue_id -> product_id -> Qloo affinity
    fit_calls: dict[str, dict[str, str]] = defaultdict(dict)
    unscored: list[str] = []
    trace = ctx.trace("match_products")

    async def one(pid: str, vt: str, rows: list[dict[str, Any]]) -> None:
        body, call_id, _ = await api.place_insights(
            ctx.svc.qloo, results_ids=[r["qloo_entity_id"] for r in rows], signal_ids=by_product[pid], trace=trace
        )
        aff = {p.entity_id: p.affinity or 0.0 for p in body.results.entities}
        here = {r["qloo_entity_id"]: aff.get(r["qloo_entity_id"], 0.0) for r in rows}
        p_, z_ = rank.percentiles(here), zscores(here)
        for r in rows:
            vid = str(r["venue_id"])
            pct[vid][pid] = round(p_[r["qloo_entity_id"]], 4)
            z[vid][pid], raw[vid][pid] = z_[r["qloo_entity_id"]], here[r["qloo_entity_id"]]
        fit_calls[pid][vt] = call_id

    for pid in by_product:
        try:
            await asyncio.gather(*[one(pid, vt, rows) for vt, rows in groups.items()])
        except QlooError as e:
            if e.code in FATAL_QLOO:
                raise
            unscored.append(pid)
            for d in (pct, z, raw):
                for v in d.values():
                    v.pop(pid, None)
            await ctx.warn("product_unscored", f"{ctx.products[pid]['name']} could not be scored ({e.code}); excluded from best product.")

    best_counts: dict[str, int] = defaultdict(int)
    th = FitThresholds()
    b = ctx.pack.buyability
    wet = {pid for pid in by_product if buyability.alcoholic(_products_text(ctx, pid), b.alcohol_keywords)}
    async with ctx.pool.acquire() as con, con.transaction():
        await con.execute("delete from venue_product_fit where run_id = $1", ctx.rid)
        for r in ranked:
            vid = str(r["venue_id"])
            zs = z.get(vid, {})
            tags = {t.get("id") for t in r["tags"] or []}
            if wet & set(zs) and (r["venue_type"] in b.licence_venue_types or tags & set(b.licence_tags)):
                dry = {pid: v for pid, v in zs.items() if pid not in wet}
                if dry:  # a café or bakery: lead with a product it can sell without a liquor licence
                    zs = dry
                elif "check_licence" not in r["flags"]:
                    await con.execute("update venue_scores set flags = array_append(flags, 'check_licence') "
                                      "where run_id = $1 and venue_id = $2", ctx.rid, r["venue_id"])
            fit = best_product(zs, raw.get(vid, {}), th)
            if fit.best:
                best_counts[ctx.products[fit.best]["name"]] += 1
            for pid, value in pct.get(vid, {}).items():
                await con.execute(
                    "insert into venue_product_fit (run_id, venue_id, product_id, percentile, is_best, margin, label, "
                    "affinity) values ($1,$2,$3,$4,$5,$6,$7,$8)",
                    ctx.rid, r["venue_id"], _uuid(pid), value, pid == fit.best, fit.margin if pid == fit.best else None,
                    fit.label if pid == fit.best else None, raw[vid].get(pid),
                )
    ctx.settings_json["fit_calls"] = fit_calls
    ctx.settings_json["fit_thresholds"] = {"method": "zscore", "clear_z": th.clear_z, "clear_raw": th.clear_raw,
                                           "close_z": th.close_z}
    ctx.settings_json["unscored_products"] = unscored
    await ctx.save_settings()
    return {"scored_products": len(by_product) - len(unscored), "best_product_counts": dict(best_counts),
            "unscored": [ctx.products[p]["name"] for p in unscored]}


# ---------------------------------------------------------------- attach_evidence (F05)
async def attach_evidence(ctx: RunContext, top_n: int = 30) -> dict[str, Any]:
    """Evidence and a template reason for every ranked venue (EVD-01); top_n only bounds the summary."""
    ranked = await _ranked(ctx)
    signal = ctx.settings_json.get("signal") or []
    names = {s["entity_id"]: s["name"] for s in signal}
    tags, tag_call = await api.audience_tags(ctx.svc.qloo, list(names), ctx.trace("attach_evidence"))
    aud = {t.key: t for t in tags if tag_kind(t.key) not in ("category", "cost_description", "inclusivity")}

    places: dict[str, Place] = {}
    target_call: dict[str, str] = {}
    for c in ctx.settings_json["calls"].values():
        for p in (await load_places(ctx, c["target"])).results.entities:
            places.setdefault(p.entity_id, p)
            target_call.setdefault(p.entity_id, c["target"])

    fits = await ctx.pool.fetch(
        "select f.*, p.name as product_name from venue_product_fit f join products p on p.id = f.product_id where f.run_id = $1",
        ctx.rid,
    )
    fit_by_venue: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in fits:
        fit_by_venue[str(f["venue_id"])].append(dict(f))

    drop = ctx.pack.reasons.drop + [v.label for v in ctx.pack.venue_types]
    overlap = {
        r["qloo_entity_id"]: plain_tags([aud[t.id].name for t in sorted(
            (t for t in places[r["qloo_entity_id"]].tags if t.id in aud), key=lambda t: -aud[t.id].affinity)], drop)
        for r in ranked if r["qloo_entity_id"] in places
    }
    overlap = distinctive(overlap)
    kinds = set(ctx.pack.reason_tag_kinds)
    evidence: list[tuple[Any, ...]] = []
    reasons: list[tuple[Any, ...]] = []
    for r in ranked:
        qid = r["qloo_entity_id"]
        pl = places.get(qid)
        if pl is None:
            continue
        p = pl
        tc = _uuid(target_call[qid])
        vid = r["venue_id"]
        generic = r["popularity_pct"] is not None
        evidence.append((vid, "qloo_affinity", "Qloo taste fit vs mass-market taste" if generic
                         else "Qloo taste fit and popularity baseline", {
            "affinity": p.affinity, "popularity": p.popularity, "target_pct": float(r["target_pct"]),
            "baseline_pct": float(r["baseline_pct"]), "lift": float(r["lift"]), "fit": float(r["fit"]),
            **({"baseline": "mass_market", "popularity_pct": float(r["popularity_pct"])} if generic else {})}, "qloo", tc))
        drivers = sorted(p.explain(), key=lambda x: -x.score)
        if drivers:
            evidence.append((vid, "qloo_explanation", "Which of your brands' fans drive this match", {
                "drivers": [{"entity_id": d.entity_id, "name": names.get(d.entity_id, d.entity_id), "score": round(d.score, 3)}
                            for d in drivers[:4]]}, "qloo", tc))
        ov = overlap.get(qid, [])
        if ov:
            evidence.append((vid, "qloo_tag_overlap", "Tastes your brands' fans over-index on, found at this venue",
                             {"tags": ov[:6]}, "qloo", _uuid(tag_call)))
        crowd = [t.name for t in p.tags if tag_kind(t.id) == "customer_identity"]
        order = ctx.pack.reason_tag_kinds
        liked = [t for t in p.tags if tag_kind(t.id) in kinds - {"customer_identity"}]
        interests = [t.name for t in sorted(liked, key=lambda t: order.index(str(tag_kind(t.id))))]
        evidence.append((vid, "qloo_venue_profile", "Who goes here (Qloo place data)", {
            "crowd": crowd[:6], "interests": interests[:8],
            "description": p.properties.get("customer_demographics_description")}, "qloo", tc))
        vf = fit_by_venue.get(str(vid), [])
        best = next((f for f in vf if f["is_best"]), None)
        runner = sorted((f for f in vf if not f["is_best"]), key=lambda f: -float(f["percentile"]))
        if best:
            fc = (ctx.settings_json.get("fit_calls") or {}).get(str(best["product_id"]), {}).get(r["venue_type"])
            evidence.append((vid, "qloo_product_fit", f"Best product (Qloo, per product): {best['product_name']}", {
                "product_id": str(best["product_id"]), "label": best["label"],
                "margin": float(best["margin"]) if best["margin"] is not None else None,
                "percentiles": {f["product_name"]: float(f["percentile"]) for f in vf},
                "affinities": {f["product_name"]: f["affinity"] for f in vf if f["affinity"] is not None}}, "qloo", _uuid(fc)))
        text = reason(
            audience_overlap=ov, crowd=crowd, interests=interests,
            driver_names=[names.get(d.entity_id, "") for d in drivers[:2]],
            best_product=best["product_name"] if best else None,
            runner_up=runner[0]["product_name"] if runner else None,
            label=best["label"] if best else "unscored",
            phrases=ctx.pack.reasons.phrases,
        )
        reasons.append((ctx.rid, vid, text))
    async with ctx.pool.acquire() as con, con.transaction():
        await con.execute("delete from venue_evidence where run_id = $1 and type <> 'contact_source' and type <> 'osm_fact'", ctx.rid)
        await con.executemany(
            "insert into venue_evidence (run_id, venue_id, type, label, value, source_kind, source_call_id) "
            "values ($1,$2,$3,$4,$5,$6,$7)",
            [(ctx.rid, *e) for e in evidence],
        )
        await con.executemany("update venue_scores set reason = $3 where run_id = $1 and venue_id = $2", reasons)
    top_aud = [t.name for t in sorted(aud.values(), key=lambda t: -t.affinity)[:5]]
    return {"venues_with_evidence": len(reasons), "evidence_items": len(evidence), "audience_tags": top_aud,
            "top_n": min(top_n, len(reasons))}


async def finish_phase(ctx: RunContext, summary: str = "") -> dict[str, Any]:
    return {"ok": True, "summary": summary[:500]}

