"""Health, workspaces, categories, city and place search, manual Qloo search, demo."""

import uuid

from fastapi import APIRouter, Depends, Query, Request

from .. import __version__
from ..agent.context import Services
from ..categories import enabled_packs
from ..errors import InvalidWorkspace, ValidationFailed
from ..external import osm
from ..qloo import api
from ..qloo.client import Trace
from ..schemas import (
    CategoryOut,
    CityHit,
    DemoOut,
    HealthOut,
    Place,
    QlooSearchItem,
    SessionIn,
    SessionOut,
    VenueTypeOut,
)
from ..security import sign, verify, workspace_id
from .deps import rate, svc

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health(s: Services = Depends(svc)) -> HealthOut:
    try:
        await s.pool.fetchval("select 1")
        db = "ok"
    except Exception:
        db = "error"
    tools_ok = await s.pool.fetchval(
        "select exists(select 1 from llm_calls where purpose = 'agent_step' and status = 'ok' "
        "and created_at > now() - interval '7 days')"
    ) if db == "ok" else False
    return HealthOut(
        status="ok" if db == "ok" else "degraded",
        db=db,
        qloo="ok" if s.qloo.configured else "unconfigured",
        llm={"provider": s.llm.name, "model": s.llm.model, "tools_ok": bool(tools_ok)},
        hunter="ok" if s.settings.hunter_api_key.get_secret_value() else "unconfigured",
        version=__version__,
    )


@router.post("/v1/workspaces/session", response_model=SessionOut)
async def session(body: SessionIn, request: Request, s: Services = Depends(svc)) -> SessionOut:
    if body.workspace_token:
        try:
            ws = verify(body.workspace_token)
            if await s.pool.fetchval("update workspaces set last_seen_at = now() where id = $1 and kind = 'anon' returning id",
                                     uuid.UUID(ws)):
                return SessionOut(workspace_token=body.workspace_token, workspace_id=ws)
        except InvalidWorkspace:
            pass
    rate(request, "session", 30, 3600)
    ws = str(await s.pool.fetchval("insert into workspaces (kind) values ('anon') returning id"))
    return SessionOut(workspace_token=sign(ws), workspace_id=ws)


@router.get("/v1/categories", response_model=list[CategoryOut])
async def categories(_: str = Depends(workspace_id)) -> list[CategoryOut]:
    return [
        CategoryOut(id=p.id, label=p.label, status=p.status,
                    venue_types=[VenueTypeOut(id=v.id, label=v.label) for v in p.venue_types])
        for p in enabled_packs().values()
    ]


@router.get("/v1/cities/search", response_model=list[CityHit])
async def cities(request: Request, q: str = Query(min_length=3, max_length=120), _: str = Depends(workspace_id),
                 s: Services = Depends(svc)) -> list[dict[str, object]]:
    rate(request, "search", 30, 60)
    st = s.settings
    return await osm.search_cities(s.pool, s.http, st.nominatim_base_url, st.osm_user_agent, q)


@router.get("/v1/places/search", response_model=list[Place])
async def places(request: Request, q: str = Query(min_length=3, max_length=160),
                 bbox: str | None = Query(default=None, description="south,west,north,east"),
                 _: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[dict[str, object]]:
    """The brand's own address or business, searched on submit (Nominatim allows no autocomplete)."""
    rate(request, "search", 30, 60)
    box = None
    if bbox:
        try:
            box = [float(v) for v in bbox.split(",")]
        except ValueError:
            box = []
        if len(box) != 4 or not (-90 <= box[0] < box[2] <= 90 and -180 <= box[1] < box[3] <= 180):
            raise ValidationFailed("bbox must be south,west,north,east")
    st = s.settings
    return await osm.search_places(s.pool, s.http, st.nominatim_base_url, st.osm_user_agent, q, box)


@router.get("/v1/places/reverse", response_model=Place)
async def reverse(request: Request, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                  _: str = Depends(workspace_id), s: Services = Depends(svc)) -> dict[str, object]:
    """Names a pin dropped on the map."""
    rate(request, "search", 30, 60)
    st = s.settings
    return await osm.reverse_place(s.pool, s.http, st.nominatim_base_url, st.osm_user_agent, lat, lon)


@router.get("/v1/qloo/search", response_model=list[QlooSearchItem])
async def qloo_search(request: Request, q: str = Query(min_length=2, max_length=120), type: str = "urn:entity:brand",
                      _: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[QlooSearchItem]:
    rate(request, "search", 30, 60)
    if not type.startswith("urn:entity:"):
        raise ValidationFailed("type must be a Qloo entity type")
    brands, call_id = await api.search(s.qloo, q, [type], Trace(step="manual_search"), take=8)
    return [QlooSearchItem(entity_id=b.entity_id, name=b.name, type=(b.types or [type])[0], popularity=b.popularity,
                           source_call_id=call_id) for b in brands]


@router.get("/v1/demo", response_model=DemoOut)
async def demo(s: Services = Depends(svc)) -> DemoOut:
    rid = s.settings.demo_run_id or None
    if not rid:
        rid = await s.pool.fetchval(
            "select r.id::text from runs r join workspaces w on w.id = r.workspace_id where w.kind = 'demo' "
            "and r.status in ('scouted','done') order by r.created_at desc limit 1")
    return DemoOut(run_id=rid, available=bool(rid and s.settings.demo_mode_enabled))
