"""Health, workspaces and sign-in, categories, city and place search, manual Qloo search, demo."""

import contextlib
import uuid
from typing import Literal

import asyncpg
import httpx
from fastapi import APIRouter, Depends, Query, Request, Response

from .. import __version__
from ..agent.context import Services
from ..categories import enabled_packs
from ..errors import AppError, InvalidWorkspace, ValidationFailed
from ..external import osm
from ..qloo import api
from ..qloo.client import Trace
from ..schemas import (
    AccountOut,
    CategoryOut,
    CityHit,
    DemoOut,
    HealthOut,
    LoginIn,
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


# Tables whose rows belong to a workspace (besides suppressions), moved when work joins an account
OWNED = ("brands", "products", "runs", "contacts", "drafts")


async def absorb(con: asyncpg.Connection, others: list[uuid.UUID], into: uuid.UUID) -> None:
    """Moves the work of other workspaces into one, then deletes them. One copy of each do-not-contact entry is kept."""
    await con.execute("insert into suppressions (workspace_id, kind, value, reason, created_at) "
                      "select $2, kind, value, reason, created_at from suppressions where workspace_id = any($1::uuid[]) "
                      "on conflict do nothing", others, into)
    for t in OWNED:
        await con.execute(f"update {t} set workspace_id = $2 where workspace_id = any($1::uuid[])", others, into)
    await con.execute("delete from workspaces where id = any($1::uuid[])", others)


@router.post("/v1/workspaces/login", response_model=AccountOut)
async def login(body: LoginIn, request: Request, s: Services = Depends(svc)) -> AccountOut:
    """Sign in (F12): checks the Supabase Auth token with Supabase once, then ties a workspace to the account. Work done
    in this browser before signing in stays: it becomes the account's workspace, or joins the one it already has."""
    rate(request, "login", 20, 3600)
    st = s.settings
    if not (st.supabase_url and st.supabase_anon_key):
        raise AppError("Sign-in is not set up on this server.", code="auth_unconfigured", status=503)
    try:
        r = await s.http.get(f"{st.supabase_url.rstrip('/')}/auth/v1/user", timeout=10,
                             headers={"apikey": st.supabase_anon_key, "Authorization": f"Bearer {body.access_token}"})
    except httpx.HTTPError as e:
        raise AppError("Could not reach the sign-in service, try again.", code="signin_failed", status=502) from e
    if r.status_code != 200:  # not 401: the web client treats 401 as a lost workspace
        raise AppError("Your sign-in has expired. Log in again.", code="signin_failed", status=400)
    user = r.json()
    uid, email = uuid.UUID(user["id"]), user.get("email")
    here = None
    with contextlib.suppress(InvalidWorkspace):
        here = uuid.UUID(verify(body.workspace_token))
    async with s.pool.acquire() as con, con.transaction():
        mine = await con.fetchval("select id from workspaces where user_id = $1", uid)
        free = here and await con.fetchval(
            "select id from workspaces where id = $1 and kind = 'anon' and user_id is null for update", here)
        if mine is None:
            mine = here if free else await con.fetchval("insert into workspaces default values returning id")
        elif here and free:
            await absorb(con, [here], mine)
        await con.execute("update workspaces set user_id = $2, email = $3, last_seen_at = now() where id = $1", mine, uid, email)
    return AccountOut(workspace_token=sign(str(mine)), workspace_id=str(mine), email=email)


@router.delete("/v1/workspaces/me", status_code=204)
async def delete_workspace(ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> Response:
    """Deletes this workspace and everything in it (brands, runs, contacts, drafts, do-not-contact list) and, when signed
    in, the Supabase account with its Google identity, at once (privacy policy). Can't be undone."""
    async with s.pool.acquire() as con, con.transaction():
        uid = await con.fetchval("delete from workspaces where id = $1 and kind = 'anon' returning user_id", uuid.UUID(ws))
        if uid and await con.fetchval("select to_regclass('auth.users') is not null"):  # Supabase only
            await con.execute("delete from auth.users where id = $1", uid)
    return Response(status_code=204)


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
    st = s.settings
    return await osm.search_places(s.pool, s.http, st.nominatim_base_url, st.osm_user_agent, q, _box(bbox))


@router.get("/v1/places/suggest", response_model=list[Place])
async def suggest(request: Request, q: str = Query(min_length=3, max_length=160),
                  kind: Literal["place", "city"] = "place",
                  bbox: str | None = Query(default=None, description="south,west,north,east"),
                  _: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[dict[str, object]]:
    """Suggestions while typing (Photon). Picking a city suggestion then makes one Nominatim city search."""
    rate(request, "suggest", 60, 60)
    st = s.settings
    return await osm.suggest(s.pool, s.http, st.photon_base_url, st.osm_user_agent, q, kind, _box(bbox))


def _box(bbox: str | None) -> list[float] | None:
    if not bbox:
        return None
    try:
        box = [float(v) for v in bbox.split(",")]
    except ValueError:
        box = []
    if len(box) != 4 or not (-90 <= box[0] < box[2] <= 90 and -180 <= box[1] < box[3] <= 180):
        raise ValidationFailed("bbox must be south,west,north,east")
    return box


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
