"""Runs (F03-F05, F09), outreach (F06-F08), trace, export, suppressions."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sse_starlette.sse import EventSourceResponse

from ..agent.context import Services
from ..categories import UNSUPPORTED, pack_for
from ..errors import AppError, Conflict, NotFound, QlooBudgetExceeded, RateLimited, ValidationFailed
from ..qloo.client import monthly_live_calls
from ..schemas import (
    Accepted,
    BestProduct,
    ContactOut,
    ContactStatusOut,
    DraftOut,
    DraftPatch,
    EvidenceOut,
    RunCreated,
    RunIn,
    RunOut,
    SuppressionIn,
    SuppressionOut,
    TraceRow,
    VenueDetail,
    VenueIdsIn,
    VenuePage,
    VenueRow,
    Weights,
)
from ..scoring import SCORING_VERSION, rank
from ..security import ip_hash, workspace_id
from ..services import runs as run_service
from ..services.contacts import is_suppressed, suppression_sets
from ..services.drafts import DraftLocked, next_status
from ..services.export import mailto, mask, to_csv
from ..services.intake import UnsupportedBusiness
from .deps import as_uuid, get_run, svc

router = APIRouter(prefix="/v1")
TERMINAL = {"scouted", "done", "failed"}
CONF_MIN = {"high": ["high"], "medium": ["high", "medium"], "low": ["high", "medium", "low"]}


# ---------------------------------------------------------------- create and read runs
@router.post("/runs", response_model=RunCreated, status_code=202)
async def create_run(body: RunIn, request: Request, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> RunCreated:
    b = await s.pool.fetchrow("select * from brands where id = $1 and workspace_id = $2", as_uuid(body.brand_id), uuid.UUID(ws))
    if b is None:
        raise NotFound("Brand not found")
    if (b["category"] == UNSUPPORTED or not (b["profile"] or {}).get("prospects_are_consumer_facing", True)) \
            and not b["unsupported_override"]:
        raise UnsupportedBusiness()
    pack = pack_for(b["category"])
    allowed_types = {v.id for v in pack.venue_types}
    if not set(body.venue_types) <= allowed_types:
        raise ValidationFailed(f"venue_types must come from {sorted(allowed_types)}")
    prods = {str(r["id"]) for r in await s.pool.fetch("select id from products where brand_id = $1", b["id"])}
    if not set(body.product_ids) <= prods:
        raise ValidationFailed("product_ids must belong to the brand")
    iph = ip_hash(request)
    used = await s.pool.fetchval(
        "select count(*) from runs where (client_ip_hash = $1 or workspace_id = $2) and created_at > now() - interval '1 day'",
        iph, uuid.UUID(ws))
    if 0 < s.settings.public_runs_per_ip_per_day <= used:  # 0 = no limit (local use)
        raise RateLimited(f"Live runs are limited to {s.settings.public_runs_per_ip_per_day} per day. The sample run is always available.")
    if s.qloo.configured and await monthly_live_calls(s.pool) >= 0.8 * s.settings.qloo_monthly_limit:
        raise QlooBudgetExceeded("The monthly Qloo budget is nearly used. Please explore the sample run instead.")
    city = {**body.city.model_dump(), "qloo_query": body.city.name}
    settings = {"entity_ids_by_product": body.entity_ids_by_product or {},
                "weights": {"target": rank.Weights().target, "lift": rank.Weights().lift},
                "base": body.base.model_dump() if body.base else None}
    async with s.pool.acquire() as con, con.transaction():
        rid = await con.fetchval(
            "insert into runs (workspace_id, brand_id, city, venue_types, scoring_version, settings, client_ip_hash) "
            "values ($1,$2,$3,$4,$5,$6,$7) returning id",
            uuid.UUID(ws), b["id"], city, list(dict.fromkeys(body.venue_types)), SCORING_VERSION, settings, iph)
        await con.executemany("insert into run_products (run_id, product_id) values ($1,$2)",
                              [(rid, uuid.UUID(p)) for p in dict.fromkeys(body.product_ids)])
    run_service.spawn(run_service.run_scout(s, str(rid)))
    return RunCreated(run_id=str(rid))


@router.get("/runs")
async def list_runs(ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[dict[str, Any]]:
    rows = await s.pool.fetch(
        "select r.id::text, r.status, r.city->>'name' as city, b.name as brand, r.created_at from runs r "
        "join brands b on b.id = r.brand_id where r.workspace_id = $1 order by r.created_at desc limit 20", uuid.UUID(ws))
    return [dict(r) for r in rows]


async def _warnings(s: Services, run_id: uuid.UUID) -> list[str]:
    rows = await s.pool.fetch("select payload from run_events where run_id = $1 and type = 'warning' order by id", run_id)
    return list(dict.fromkeys(r["payload"].get("message", "") for r in rows if r["payload"].get("code") != "guard_refused"))


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run_out(run_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> RunOut:
    r = await get_run(s, ws, run_id)
    b = await s.pool.fetchrow("select id::text, name, profile, category from brands where id = $1", r["brand_id"])
    prods = await s.pool.fetch(
        "select p.id::text, p.name, p.kind from products p join run_products rp on rp.product_id = p.id "
        "where rp.run_id = $1 order by p.position", r["id"])
    st = r["settings"] or {}
    return RunOut(
        id=str(r["id"]), status=r["status"], phase=r["phase"], orchestration=r["orchestration"],
        orchestration_reason=r["orchestration_reason"], brand=dict(b), products=[dict(p) for p in prods], city=r["city"],
        venue_types=list(r["venue_types"]), counters=r["counters"] or {}, warnings=await _warnings(s, r["id"]),
        resolution=st.get("resolution") or {}, scoring_version=r["scoring_version"],
        weights=st.get("weights") or {"target": 0.7, "lift": 0.3}, error_code=r["error_code"],
        error_message=r["error_message"], is_demo=r["workspace_kind"] == "demo", created_at=r["created_at"],
        finished_at=r["finished_at"], base=st.get("base"),
    )


@router.get("/runs/{run_id}/events")
async def events(run_id: str, request: Request, last_event_id: int = 0, ws: str = Depends(workspace_id),
                 s: Services = Depends(svc)) -> EventSourceResponse:
    """SSE with replay: resumes after Last-Event-ID (header) or ?last_event_id= (AGT-04)."""
    r = await get_run(s, ws, run_id)
    last = int(request.headers.get("last-event-id") or last_event_id or 0)

    async def gen() -> Any:
        nonlocal last
        quiet = 0
        deadline = asyncio.get_running_loop().time() + 600
        while asyncio.get_running_loop().time() < deadline:
            if await request.is_disconnected():
                return
            rows = await s.pool.fetch("select id, type, payload from run_events where run_id = $1 and id > $2 order by id",
                                      r["id"], last)
            for e in rows:
                last = e["id"]
                yield {"id": str(e["id"]), "event": e["type"], "data": json.dumps(e["payload"], default=str)}
            status = await s.pool.fetchval("select status from runs where id = $1", r["id"])
            quiet = quiet + 1 if (status in TERMINAL and not rows) else 0
            if quiet >= 2:
                yield {"event": "end", "data": json.dumps({"status": status})}
                return
            await asyncio.sleep(0.4)

    return EventSourceResponse(gen(), ping=15)


# ---------------------------------------------------------------- venues
VENUE_SQL = """
select vs.*, v.name, v.properties->>'neighborhood' as neighborhood, v.address, v.website, v.lat, v.lon, v.properties,
  (select count(*) from venue_evidence e where e.run_id = vs.run_id and e.venue_id = vs.venue_id) as evidence_count,
  coalesce(cc.status, 'not_checked') as contact_status, cc.checked_sources,
  bp.product_id as best_product_id, p.name as best_product_name, bp.label as best_label, bp.margin as best_margin
from venue_scores vs join venues v on v.id = vs.venue_id
left join contact_checks cc on cc.run_id = vs.run_id and cc.venue_id = vs.venue_id
left join venue_product_fit bp on bp.run_id = vs.run_id and bp.venue_id = vs.venue_id and bp.is_best
left join products p on p.id = bp.product_id
where vs.run_id = $1
"""


def _row(r: Any) -> VenueRow:
    return VenueRow(
        venue_id=str(r["venue_id"]), rank=r["rank"], name=r["name"], venue_type=r["venue_type"],
        neighborhood=r["neighborhood"], lat=r["lat"], lon=r["lon"], fit=float(r["fit"]), lift=float(r["lift"]), target_pct=float(r["target_pct"]),
        baseline_pct=float(r["baseline_pct"]), confidence=r["confidence"], flags=list(r["flags"]),
        best_product=BestProduct(product_id=str(r["best_product_id"]), name=r["best_product_name"], label=r["best_label"],
                                 margin=float(r["best_margin"]) if r["best_margin"] is not None else None)
        if r["best_product_id"] else None,
        reason=r["reason"], evidence_count=r["evidence_count"], contact_status=r["contact_status"],
    )


@router.get("/runs/{run_id}/venues", response_model=VenuePage)
async def venues(run_id: str, type: str | None = None, confidence: str | None = Query(None, pattern="^(high|medium|low)$"),
                 product_id: str | None = None, sort: str = Query("fit", pattern="^(fit|lift)$"),
                 limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
                 ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> VenuePage:
    r = await get_run(s, ws, run_id)
    sql, args = VENUE_SQL, [r["id"]]
    if type:
        args.append(type)
        sql += f" and vs.venue_type = ${len(args)}"
    if confidence:
        args.append(CONF_MIN[confidence])
        sql += f" and vs.confidence = any(${len(args)}::text[])"
    if product_id:
        args.append(as_uuid(product_id))
        sql += f" and bp.product_id = ${len(args)}"
    rows = await s.pool.fetch(sql + (" order by vs.lift desc, vs.rank" if sort == "lift" else " order by vs.rank"), *args)
    return VenuePage(items=[_row(x) for x in rows[offset: offset + limit]], total=len(rows), warnings=await _warnings(s, r["id"]))


def _masked(c: dict[str, Any], demo: bool) -> dict[str, Any]:
    return {**c, "email": mask(c["email"])} if demo else c


def _contact(c: Any, demo: bool) -> ContactOut:
    d = _masked(dict(c), demo)
    return ContactOut(id=str(d["id"]), email=d["email"], role=d["role"], type=d["type"], source=d["source"],
                      confidence=d["confidence"], verification_status=d["verification_status"], sources=d["sources"] or [],
                      is_primary=d["is_primary"])


@router.get("/runs/{run_id}/venues/{venue_id}", response_model=VenueDetail)
async def venue_detail(run_id: str, venue_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> VenueDetail:
    r = await get_run(s, ws, run_id)
    demo = r["workspace_kind"] == "demo"
    v = await s.pool.fetchrow(VENUE_SQL + " and vs.venue_id = $2", r["id"], as_uuid(venue_id))
    if v is None:
        raise NotFound("Venue not found in this run")
    fits = await s.pool.fetch(
        "select f.product_id::text, p.name, f.percentile, f.is_best, f.label, f.margin from venue_product_fit f "
        "join products p on p.id = f.product_id where f.run_id = $1 and f.venue_id = $2 order by f.percentile desc",
        r["id"], v["venue_id"])
    ev = await s.pool.fetch("select * from venue_evidence where run_id = $1 and venue_id = $2 order by captured_at, type",
                            r["id"], v["venue_id"])
    cs = await s.pool.fetch("select * from contacts where run_id = $1 and venue_id = $2 order by is_primary desc",
                            r["id"], v["venue_id"])
    now = datetime.now(UTC)
    evidence = []
    for e in ev:
        val = dict(e["value"])
        if demo and e["type"] == "contact_source" and val.get("email"):
            val["email"] = mask(val["email"])
        evidence.append(EvidenceOut(id=str(e["id"]), type=e["type"], label=e["label"], value=val, source_kind=e["source_kind"],
                                    source_call_id=str(e["source_call_id"]) if e["source_call_id"] else None,
                                    captured_at=e["captured_at"], stale=now - e["captured_at"] > timedelta(days=30)))
    props = v["properties"] or {}
    return VenueDetail(
        venue=_row(v), address=v["address"], website=v["website"], phone=props.get("phone"), lat=v["lat"], lon=v["lon"],
        description=props.get("short_description"),
        product_fit=[{**dict(f), "percentile": float(f["percentile"]),
                      "margin": float(f["margin"]) if f["margin"] is not None else None} for f in fits],
        evidence=evidence, contacts=[_contact(c, demo) for c in cs], checked_sources=list(v["checked_sources"] or []),
        base=(r["settings"] or {}).get("base"),
    )


@router.post("/runs/{run_id}/rescore", response_model=VenuePage)
async def rescore(run_id: str, body: Weights, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> VenuePage:
    """New weights over stored scores; zero Qloo calls."""
    r = await get_run(s, ws, run_id, write=True)
    w = rank.Weights(target=body.target, lift=body.lift)
    rows = await s.pool.fetch("select venue_id, target_pct, lift from venue_scores where run_id = $1", r["id"])
    scored = sorted(((x["venue_id"], rank.fit(float(x["target_pct"]), float(x["lift"]), w), float(x["target_pct"])) for x in rows),
                    key=lambda t: (-t[1], -t[2], str(t[0])))
    async with s.pool.acquire() as con, con.transaction():
        await con.executemany("update venue_scores set fit = $3, rank = $4 where run_id = $1 and venue_id = $2",
                              [(r["id"], vid, f, i) for i, (vid, f, _) in enumerate(scored, 1)])
        await con.execute("update runs set settings = settings || $2::jsonb where id = $1", r["id"],
                          {"weights": {"target": w.target, "lift": w.lift}})
    return await venues(run_id, None, None, None, "fit", 100, 0, ws, s)


# ---------------------------------------------------------------- trace (AGT-05)
@router.get("/runs/{run_id}/trace", response_model=list[TraceRow])
async def trace(run_id: str, kind: str | None = Query(None, pattern="^(qloo|external|llm|tool)$"),
                ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[TraceRow]:
    r = await get_run(s, ws, run_id)
    out: list[TraceRow] = []
    if kind in (None, "qloo"):
        for q in await s.pool.fetch("select * from qloo_calls where run_id = $1 order by created_at", r["id"]):
            out.append(TraceRow(kind="qloo", id=str(q["id"]), at=q["created_at"], step=q["step"], name=q["endpoint"], detail={
                "params": q["params"], "status": q["status"], "cache_hit": q["cache_hit"], "duration_ms": q["duration_ms"],
                "result_count": q["result_count"], "warnings": q["warnings"]}))
    if kind in (None, "external"):
        for x in await s.pool.fetch("select * from external_calls where run_id = $1 order by created_at", r["id"]):
            params = dict(x["params"])
            if r["workspace_kind"] == "demo" and "email" in params:
                params["email"] = mask(params["email"])
            out.append(TraceRow(kind="external", id=str(x["id"]), at=x["created_at"], step=x["service"], name=x["endpoint"],
                                detail={"params": params, "status": x["status"], "cache_hit": x["cache_hit"],
                                        "duration_ms": x["duration_ms"]}))
    if kind in (None, "llm"):
        for m in await s.pool.fetch("select * from llm_calls where run_id = $1 order by created_at", r["id"]):
            out.append(TraceRow(kind="llm", id=str(m["id"]), at=m["created_at"], step=m["purpose"], name=f"{m['provider']}/{m['model']}",
                                detail={"status": m["status"], "duration_ms": m["duration_ms"], "prompt_version": m["prompt_version"],
                                        "input_tokens": m["input_tokens"], "output_tokens": m["output_tokens"], **(m["detail"] or {})}))
    if kind in (None, "tool"):
        for e in await s.pool.fetch("select * from run_events where run_id = $1 and type in ('tool_call','step_done','phase_started','phase_done') order by id", r["id"]):
            p = e["payload"]
            out.append(TraceRow(kind="tool", id=str(e["id"]), at=e["created_at"], step=e["type"],
                                name=p.get("tool") or p.get("phase") or e["type"], detail=p))
    out.sort(key=lambda t: t.at)
    return out


# ---------------------------------------------------------------- outreach (F06, F07)
async def _ranked_ids(s: Services, rid: uuid.UUID, ids: list[str]) -> list[str]:
    want = [as_uuid(v) for v in ids]
    found = {str(x["venue_id"]) for x in await s.pool.fetch(
        "select venue_id from venue_scores where run_id = $1 and venue_id = any($2::uuid[])", rid, want)}
    if len(found) != len(set(ids)):
        raise ValidationFailed("venue_ids must belong to this run")
    return [v for v in dict.fromkeys(ids)]


@router.post("/runs/{run_id}/contacts", response_model=Accepted, status_code=202)
async def start_contacts(run_id: str, body: VenueIdsIn, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> Accepted:
    r = await get_run(s, ws, run_id, write=True)
    if r["status"] not in ("scouted", "done"):
        raise Conflict(f"Run is {r['status']}; wait for ranking to finish.")
    if len(body.venue_ids) > s.settings.max_outreach_venues_per_run:
        raise ValidationFailed(f"Select at most {s.settings.max_outreach_venues_per_run} venues.")
    ids = await _ranked_ids(s, r["id"], body.venue_ids)
    # Running before the reply, so the outreach page shows progress at once
    await s.pool.execute("update runs set status = 'outreach_running', phase = 'outreach' where id = $1", r["id"])
    run_service.spawn(run_service.run_outreach(s, run_id, ids), run_id)
    return Accepted(run_id=run_id, status="outreach_running")


@router.post("/runs/{run_id}/cancel", response_model=Accepted, status_code=202)
async def cancel_outreach(run_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> Accepted:
    """Stops a running outreach; what it found so far is kept. Does nothing otherwise."""
    r = await get_run(s, ws, run_id, write=True)
    if r["status"] != "outreach_running":
        return Accepted(run_id=run_id, status=r["status"])
    await run_service.cancel_outreach(s, run_id)
    return Accepted(run_id=run_id, status="scouted")


@router.get("/runs/{run_id}/contacts", response_model=list[ContactStatusOut])
async def get_contacts(run_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[ContactStatusOut]:
    r = await get_run(s, ws, run_id)
    demo = r["workspace_kind"] == "demo"
    checks = await s.pool.fetch(
        "select cc.*, v.name, vs.rank from contact_checks cc join venues v on v.id = cc.venue_id "
        "join venue_scores vs on vs.run_id = cc.run_id and vs.venue_id = cc.venue_id where cc.run_id = $1 order by vs.rank", r["id"])
    cs = await s.pool.fetch("select * from contacts where run_id = $1 order by is_primary desc", r["id"])
    sup_e, sup_d = await suppression_sets(s.pool, ws)
    by_v: dict[str, list[ContactOut]] = {}
    for c in cs:
        if not is_suppressed(c["email"], sup_e, sup_d):
            by_v.setdefault(str(c["venue_id"]), []).append(_contact(c, demo))
    out = []
    for c in checks:
        contacts = by_v.get(str(c["venue_id"]), [])
        status = c["status"]
        if status == "found" and not contacts:
            status = "suppressed"
        out.append(ContactStatusOut(venue_id=str(c["venue_id"]), name=c["name"], rank=c["rank"], status=status,
                                    checked_sources=list(c["checked_sources"] or []), contacts=contacts))
    return out


@router.post("/runs/{run_id}/drafts", response_model=Accepted, status_code=202)
async def start_drafts(run_id: str, body: VenueIdsIn, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> Accepted:
    r = await get_run(s, ws, run_id, write=True)
    if r["status"] not in ("scouted", "done"):
        raise Conflict(f"Run is {r['status']}.")
    ids = await _ranked_ids(s, r["id"], body.venue_ids)
    run_service.spawn(run_service.run_outreach(s, run_id, ids, drafts_only=True), run_id)
    return Accepted(run_id=run_id, status="outreach_running")


def _draft(d: Any, demo: bool) -> DraftOut:
    email = mask(d["email"]) if demo else d["email"]
    ok = d["status"] in ("approved", "exported") and not demo
    return DraftOut(
        id=str(d["id"]), venue_id=str(d["venue_id"]), venue_name=d["venue_name"], contact_id=str(d["contact_id"]),
        contact_email=email, subject=d["subject"], body=d["body"], cited_evidence_ids=[str(x) for x in d["cited_evidence_ids"]],
        source=d["source"], status=d["status"], model=d["model"], mailto=mailto(d["email"], d["subject"], d["body"]) if ok else None,
        updated_at=d["updated_at"], approved_at=d["approved_at"],
    )


DRAFT_SQL = ("select d.*, v.name as venue_name, c.email from drafts d join venues v on v.id = d.venue_id "
             "join contacts c on c.id = d.contact_id")


@router.get("/runs/{run_id}/drafts", response_model=list[DraftOut])
async def get_drafts(run_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[DraftOut]:
    r = await get_run(s, ws, run_id)
    rows = await s.pool.fetch(DRAFT_SQL + " join venue_scores vs on vs.run_id = d.run_id and vs.venue_id = d.venue_id "
                              "where d.run_id = $1 order by vs.rank", r["id"])
    sup_e, sup_d = await suppression_sets(s.pool, ws)
    return [_draft(d, r["workspace_kind"] == "demo") for d in rows if not is_suppressed(d["email"], sup_e, sup_d)]


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
async def patch_draft(draft_id: str, body: DraftPatch, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> DraftOut:
    d = await s.pool.fetchrow(DRAFT_SQL + " where d.id = $1 and d.workspace_id = $2", as_uuid(draft_id), uuid.UUID(ws))
    if d is None:
        raise NotFound("Draft not found")
    subject = body.subject if body.subject is not None else d["subject"]
    text = body.body if body.body is not None else d["body"]
    edited = subject != d["subject"] or text != d["body"]
    if body.status == "approved":
        sup_e, sup_d = await suppression_sets(s.pool, ws)
        if is_suppressed(d["email"], sup_e, sup_d):
            raise Conflict("This contact is on your do-not-contact list.")
    status = next_status(d["status"], edited=edited, approve=body.status == "approved", export=body.status == "exported")
    await s.pool.execute(
        "update drafts set subject = $2, body = $3, status = $4, updated_at = now(), "
        "approved_at = case when $4 = 'approved' then now() when $4 = 'edited' then null else approved_at end, "
        "exported_at = case when $4 = 'exported' then now() else exported_at end where id = $1",
        d["id"], subject, text, status)
    d2 = await s.pool.fetchrow(DRAFT_SQL + " where d.id = $1", d["id"])
    return _draft(d2, False)


@router.post("/drafts/{draft_id}/regenerate", response_model=Accepted, status_code=202)
async def regenerate(draft_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> Accepted:
    d = await s.pool.fetchrow("select * from drafts where id = $1 and workspace_id = $2", as_uuid(draft_id), uuid.UUID(ws))
    if d is None:
        raise NotFound("Draft not found")
    if d["status"] in ("approved", "exported"):
        raise DraftLocked()
    run_service.spawn(run_service.run_outreach(s, str(d["run_id"]), [str(d["venue_id"])], drafts_only=True), str(d["run_id"]))
    return Accepted(run_id=str(d["run_id"]), status="outreach_running")


@router.get("/runs/{run_id}/export.csv")
async def export_csv(run_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> Response:
    r = await get_run(s, ws, run_id)
    demo = r["workspace_kind"] == "demo"
    rows = await s.pool.fetch(VENUE_SQL + " order by vs.rank", r["id"])
    cs = {str(c["venue_id"]): c for c in await s.pool.fetch("select * from contacts where run_id = $1 and is_primary", r["id"])}
    ds = {str(d["venue_id"]): d for d in await s.pool.fetch("select * from drafts where run_id = $1", r["id"])}
    sup_e, sup_d = await suppression_sets(s.pool, ws)
    out, exported = [], []
    for v in rows:
        vid = str(v["venue_id"])
        c, d = cs.get(vid), ds.get(vid)
        if c and is_suppressed(c["email"], sup_e, sup_d):
            c, d = None, None
        approved = d is not None and d["status"] in ("approved", "exported")
        out.append({
            "rank": v["rank"], "venue_name": v["name"], "venue_type": v["venue_type"], "city": r["city"].get("name"),
            "fit": round(float(v["fit"]) * 100), "lift": round(float(v["lift"]) * 100), "confidence": v["confidence"],
            "best_product": v["best_product_name"], "reason": v["reason"],
            "contact_email": (mask(c["email"]) if demo else c["email"]) if c else None,
            "contact_role": c["role"] if c else None, "contact_source": c["source"] if c else None,
            "verification_status": c["verification_status"] if c else None,
            "draft_status": d["status"] if d else None,
            "draft_subject": d["subject"] if approved and d else None, "draft_body": d["body"] if approved and d else None,
        })
        if approved and d and not demo:
            exported.append(d["id"])
    if exported:
        await s.pool.execute("update drafts set status = 'exported', exported_at = now() where id = any($1::uuid[])", exported)
    name = f"tasteroute-{r['city'].get('name', 'run')}-{str(r['id'])[:8]}.csv".replace(" ", "-").lower()
    return Response(to_csv(out), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- suppressions (F08)
@router.get("/suppressions", response_model=list[SuppressionOut])
async def list_suppressions(q: str | None = None, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[SuppressionOut]:
    rows = await s.pool.fetch(
        "select * from suppressions where workspace_id = $1 and ($2::text is null or value ilike '%' || $2 || '%') "
        "order by created_at desc", uuid.UUID(ws), q)
    return [SuppressionOut(id=str(x["id"]), kind=x["kind"], value=str(x["value"]), reason=x["reason"], created_at=x["created_at"]) for x in rows]


@router.post("/suppressions", response_model=SuppressionOut, status_code=201)
async def add_suppression(body: SuppressionIn, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> SuppressionOut:
    v = body.value.strip().lower()
    if body.kind == "email" and ("@" not in v or v.startswith("@") or "." not in v.rsplit("@", 1)[-1]):
        raise ValidationFailed("Enter a full email address")
    if body.kind == "domain":
        v = v.removeprefix("http://").removeprefix("https://").removeprefix("www.").split("/")[0].lstrip("@")
        if "." not in v or "@" in v:
            raise ValidationFailed("Enter a domain like cafe-example.com")
    row = await s.pool.fetchrow(
        "insert into suppressions (workspace_id, kind, value, reason) values ($1,$2,$3,$4) on conflict (workspace_id, kind, value) "
        "do update set reason = excluded.reason returning *", uuid.UUID(ws), body.kind, v, body.reason)
    return SuppressionOut(id=str(row["id"]), kind=row["kind"], value=str(row["value"]), reason=row["reason"], created_at=row["created_at"])


@router.delete("/suppressions/{sid}", status_code=204)
async def delete_suppression(sid: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> Response:
    n = await s.pool.execute("delete from suppressions where id = $1 and workspace_id = $2", as_uuid(sid), uuid.UUID(ws))
    if n.endswith(" 0"):
        raise NotFound("Not found")
    return Response(status_code=204)


__all__ = ["router", "AppError"]
