"""Agent tools. Deterministic over Qloo responses: the LLM only decides when to call them (AGT-06)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from ..errors import AppError, QlooContractViolation, QlooError
from ..qloo import api
from ..qloo.client import stored_response
from ..qloo.compact import tag_kind
from ..qloo.guards import guard_places
from ..qloo.models import InsightsBody, Place
from ..scoring import SCORING_VERSION, buyability, rank
from ..scoring.fit import FitThresholds, best_product, zscores
from ..scoring.reasons import distinctive, plain_tags, reason
from . import rules
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
            res = {"status": "resolved", "entities": p["entities"], "dropped": [],
                   "message": "Confirmed by you" if p["entities"] else "No brand Qloo knows was found for it in step 3"}
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
                           "dropped": res["dropped"], "entities": [e["name"] for e in ents],
                           "known_by_name": any(e["role"] == "self" for e in ents), "weak": rules.weak(ents),
                           "suggest_rounds": 0}
        if not ents:
            await ctx.warn("product_unresolved", f"{p['name']}: {res['message']}")
    ctx.settings_json["resolution"] = resolution
    await ctx.save_settings()
    return _resolution_summary(ctx)  # no entities at all fails in rank_venues, after the agent could suggest more


def _resolution_summary(ctx: RunContext) -> dict[str, Any]:
    res = ctx.settings_json["resolution"]
    return {
        "products": [{"product_id": pid, "name": ctx.products[pid]["name"], "status": r["status"],
                      "known_by_name": r["known_by_name"], "similar_brands": r["entities"], "weak": r["weak"],
                      "suggest_rounds": r["suggest_rounds"]} for pid, r in res.items()],
        "rule": f"weak = known only through fewer than {rules.MIN_COMPARABLES} similar brands; "
                f"suggest_more_comparables at most {rules.MAX_SUGGEST_ROUNDS} times per product",
        "needs_more_comparables": rules.needs_comparables(res),
    }


async def suggest_more_comparables(ctx: RunContext, product_id: str, reason: str = "") -> dict[str, Any]:
    """The LLM suggests similar brands and Qloo /search must confirm each one (ENT-02); at most 2 are added per call."""
    from ..errors import LLMBadResponse, LLMUnavailable
    from ..services.resolve import best_match, entity, suggest_comparables

    r = ctx.settings_json["resolution"][product_id]
    p = ctx.products[product_id]
    have = {x["qloo_entity_id"] for x in await ctx.pool.fetch(
        "select qloo_entity_id from product_entities where run_id = $1 and product_id = $2", ctx.rid, _uuid(product_id))}
    try:
        names = await suggest_comparables(ctx.svc, ctx.brand, p, ctx.run_id, exclude=r["entities"] + r["dropped"])
    except (LLMUnavailable, LLMBadResponse):
        names = []
    trace, context = ctx.trace("suggest_more_comparables"), _products_text(ctx, product_id)
    added: list[str] = []
    dropped: list[str] = []
    for name in names:
        if len(added) >= 2:
            break
        try:
            brands, call_id = await api.search(ctx.svc.qloo, name, ctx.pack.product_entity_types, trace)
        except QlooError as err:
            if err.code in FATAL_QLOO:
                raise
            dropped.append(name)
            continue
        m = best_match(name, brands, context)
        if not m or m[0].entity_id in have:
            dropped.append(name)
            continue
        found = entity(m[0], "comparable", m[1], call_id)
        await ctx.pool.execute(
            "insert into product_entities (run_id, product_id, qloo_entity_id, name, entity_type, role, similarity, "
            "source_call_id) values ($1,$2,$3,$4,$5,$6,$7,$8) on conflict do nothing",
            ctx.rid, p["id"], found["entity_id"], found["name"], found["type"], found["role"], found["similarity"],
            _uuid(call_id))
        have.add(found["entity_id"])
        added.append(found["name"])
    r["entities"] += added
    r["dropped"] += dropped
    r["suggest_rounds"] += 1
    r["status"] = "resolved" if r["entities"] else "unresolved"
    r["weak"] = len(r["entities"]) < rules.MIN_COMPARABLES and not r["known_by_name"]
    await ctx.save_settings()
    if added:
        why = f" Its reason: {reason.rstrip('.')}." if reason and ctx.actor == "AI agent" else ""
        await ctx.warn("comparables_added", f"{p['name']}: the {_who(ctx)} added {', '.join(added)} as similar brands "
                                            f"(Qloo confirmed each), because it was known through fewer than "
                                            f"{rules.MIN_COMPARABLES}.{why}")
    return {"product": p["name"], "added": added, "not_in_qloo": dropped, "similar_brands": r["entities"],
            "still_weak": r["weak"], "needs_more_comparables": rules.needs_comparables(ctx.settings_json["resolution"])}


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
    ids = [s["qloo_entity_id"] for s in signal]
    calls = await asyncio.gather(*[_rank_type(ctx, vt, ids, ctx.trace("rank_venues")) for vt in types])
    ctx.settings_json["calls"] = dict(calls)
    ctx.settings_json["signal"] = [{"entity_id": s["qloo_entity_id"], "name": s["name"]} for s in signal]
    ctx.settings_json.setdefault("weights", {"target": rank.Weights().target, "lift": rank.Weights().lift})
    ctx.settings_json["scoring_version"] = SCORING_VERSION
    ctx.settings_json["max_venues"] = max_venues
    await ctx.save_settings()
    return _with_type_rule(ctx, await score_from_stored(ctx, max_venues=max_venues))


def qualified_city(city: dict[str, Any]) -> str | None:
    """'Portland, Maine' for a US city: the state from the geocoder's display name (verified 2026-10-20, QLO-12)."""
    parts = (city.get("display_name") or "").split(", ")
    return f"{city['name']}, {parts[-2]}" if (city.get("country") or "").lower() == "us" and len(parts) >= 3 else None


async def _rank_type(ctx: RunContext, vt: str, ids: list[str], trace: Any) -> tuple[str, dict[str, str]]:
    vtype = ctx.pack.venue_type(vt)
    assert vtype is not None
    city_q = ctx.city.get("qloo_query") or ctx.city["name"]

    async def target(q: str) -> tuple[InsightsBody, str]:
        body, call, _ = await api.place_insights(ctx.svc.qloo, city_query=q, tags=vtype.qloo_tags, signal_ids=ids,
                                                 explain=True, trace=trace)
        return body, call

    def elsewhere(b: InsightsBody) -> bool:
        try:
            return not guard_places(b.results.entities, required_tags=vtype.qloo_tags, bbox=ctx.city.get("bbox")).kept
        except QlooContractViolation:  # every venue failed the guard
            return True

    body, tcall = await target(city_q)
    alt = qualified_city(ctx.city)
    if alt and alt != city_q and body.results.entities and elsewhere(body):
        # A bare name can land in another city ("Portland" -> Oregon); the bbox guard sees it, so ask with the state.
        body, tcall = await target(alt)
        city_q = alt
    generic = ctx.pack.baseline_entities if ctx.pack.baseline_signal == "fixed_entities" else []
    if generic:  # the same venues under mass-market brands (D-23): same number of calls, the second needs the first
        venues = [p.entity_id for p in body.results.entities]
        _, gcall, _ = await api.place_insights(ctx.svc.qloo, results_ids=venues, signal_ids=generic, trace=trace)
        return vt, {"target": tcall, "generic": gcall}
    _, bcall, _ = await api.place_insights(ctx.svc.qloo, city_query=city_q, tags=vtype.qloo_tags, trace=trace)
    return vt, {"target": tcall, "baseline": bcall}


def _who(ctx: RunContext) -> str:
    return "AI agent" if ctx.actor == "AI agent" else "fixed plan"


def _with_type_rule(ctx: RunContext, summary: dict[str, Any]) -> dict[str, Any]:
    added = ctx.settings_json.get("added_types") or []
    pack_types = [v.id for v in ctx.pack.venue_types]
    return {**summary, "run_venue_types": ctx.venue_types,
            "thin_types": rules.thin_types(summary["by_type"], ctx.venue_types),
            "types_you_can_add": [t for t in pack_types if t not in ctx.venue_types][:4] if len(added) < rules.MAX_ADDED_TYPES else [],
            "rule": f"thin = fewer than {rules.MIN_VENUES_PER_TYPE} ranked venues; add_venue_type at most "
                    f"{rules.MAX_ADDED_TYPES} times per run",
            "suggested_type": rules.type_to_add(summary["by_type"], ctx.venue_types, pack_types, added)}


async def add_venue_type(ctx: RunContext, type_id: str, reason: str = "") -> dict[str, Any]:
    """Ranks one more venue type from the pack and re-scores everything from stored responses (2 Qloo calls)."""
    thin = rules.thin_types(ctx.settings_json.get("by_type") or {}, ctx.venue_types)
    ids = [s["entity_id"] for s in ctx.settings_json["signal"]]
    _, calls = await _rank_type(ctx, type_id, ids, ctx.trace("add_venue_type"))
    ctx.venue_types.append(type_id)
    ctx.settings_json["calls"][type_id] = calls
    ctx.settings_json.setdefault("added_types", []).append(type_id)
    await ctx.pool.execute("update runs set venue_types = $2 where id = $1", ctx.rid, ctx.venue_types)
    await ctx.save_settings()
    summary = await score_from_stored(ctx, max_venues=ctx.settings_json.get("max_venues"))
    def label(t: str) -> str:
        return (ctx.pack.venue_type(t) or ctx.pack.venue_types[0]).label.lower()

    few = ", ".join(f"{n} {label(t)}" for t, n in thin.items())
    why = f" Its reason: {reason.rstrip('.')}." if reason and ctx.actor == "AI agent" else ""
    await ctx.warn("venue_type_added", f"The {_who(ctx)} added {label(type_id)} because only {few} came back (fewer "
                                       f"than {rules.MIN_VENUES_PER_TYPE} of a type).{why}")
    return {**_with_type_rule(ctx, summary), "added": type_id}


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
    counts = [f"{k} {what}" for k, what in ((n["chain"], "chain venues"), (n["signal_brand_venue"], "venues of brands you resemble")) if k]
    return (f"Hidden by default, listed after the rest: {' and '.join(counts)} "
            f"({', '.join(names[:8])}{'…' if len(names) > 8 else ''}).")


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
    spread: dict[str, float] = {}  # max - min Qloo affinity per type: how much taste separates the venues
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
        affs = [c.affinity for c in cands if c.affinity is not None]
        spread[vt] = round(max(affs) - min(affs), 3) if affs else 0.0
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
        ctx.settings_json["rank_warnings"] = [{"code": c, "message": m} for c, m in warnings]  # the latest pass wins
        await ctx.save_settings()
        for code, msg in warnings:
            await ctx.warn(code, msg)
    return {
        "ranked": len(merged),
        "by_type": by_type,
        "affinity_spread": spread,
        "top": [places[s.venue_id].name for s in merged[:5]],
        "high_confidence": sum(1 for s in merged if s.confidence == "high"),
        "high_confidence_share": round(sum(1 for s in merged if s.confidence == "high") / len(merged), 2),
        "hidden": {f: sum(f in s.flags for s in merged) for f in buyability.HIDDEN},
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
    labels: dict[str, int] = defaultdict(int)
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
                labels[fit.label] += 1
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
            "tie_share": round(labels["tie"] / max(sum(labels.values()), 1), 2),
            "unscored": [ctx.products[p]["name"] for p in unscored]}


# ---------------------------------------------------------------- attach_evidence (F05)
MUSIC_REASON_PCT = 0.75  # the music clause appears for the top quarter of a venue type


async def _music(ctx: RunContext, ranked: list[dict[str, Any]], signal_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Cross-domain taste (EVD-06): the artists your brands' fans over-index on, then how each ranked venue scores with
    those artists' fans, per venue type. An explanation only; it never changes fit (D-30, the stockist backtest)."""
    trace = ctx.trace("attach_evidence")
    try:
        artists, _ = await api.taste_entities(ctx.svc.qloo, signal_ids, take=5, trace=trace)
        art = {a.entity_id: a.name for a in artists}
        if not art:
            return {}
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in ranked:
            by_type[r["venue_type"]].append(r)
        out: dict[str, dict[str, Any]] = {}
        for rows in by_type.values():
            got: dict[str, tuple[Place, str]] = {}
            for i in range(0, len(rows), api.MAX_TAKE):
                body, call_id, _ = await api.place_insights(
                    ctx.svc.qloo, results_ids=[r["qloo_entity_id"] for r in rows[i:i + api.MAX_TAKE]],
                    signal_ids=list(art), explain=True, trace=trace)
                got |= {p.entity_id: (p, call_id) for p in body.results.entities if p.affinity is not None}
            pct = rank.percentiles({q: p.affinity or 0.0 for q, (p, _) in got.items()})
            for q, (p, call_id) in got.items():
                top = [art[d.entity_id] for d in sorted(p.explain(), key=lambda d: -d.score) if d.entity_id in art][:2]
                out[q] = {"artists": top, "fans_like": list(art.values()), "affinity": p.affinity, "pct": round(pct[q], 4),
                          "call": call_id}
        return out
    except QlooError as e:
        if e.code in FATAL_QLOO:
            raise
        await ctx.warn("music_unavailable", f"Music taste could not be read from Qloo ({e.code}); reasons leave it out.")
        return {}


async def attach_evidence(ctx: RunContext, top_n: int = 30) -> dict[str, Any]:
    """Evidence and a template reason for every ranked venue (EVD-01); top_n only bounds the summary."""
    ranked = await _ranked(ctx)
    signal = ctx.settings_json.get("signal") or []
    names = {s["entity_id"]: s["name"] for s in signal}
    tags, tag_call = await api.audience_tags(ctx.svc.qloo, list(names), ctx.trace("attach_evidence"))
    aud = {t.key: t for t in tags if tag_kind(t.key) not in ("category", "cost_description", "inclusivity")}
    music = await _music(ctx, ranked, list(names))

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
        m = music.get(qid)
        if m:
            evidence.append((vid, "qloo_cross_domain", "Music your brands' fans like, and how this venue scores with its fans",
                             {k: m[k] for k in ("artists", "fans_like", "affinity", "pct")} | {"domain": "music"},
                             "qloo", _uuid(m["call"])))
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
            music=m["artists"] if m and m["pct"] >= MUSIC_REASON_PCT else None,
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
            "music_fans_like": next((m["fans_like"] for m in music.values()), []), "top_n": min(top_n, len(reasons))}


async def finish_phase(ctx: RunContext, summary: str = "") -> dict[str, Any]:
    return {"ok": True, "summary": summary[:500]}

