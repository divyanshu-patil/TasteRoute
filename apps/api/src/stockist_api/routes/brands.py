"""Brands and products (F01), resolution preview and entity edits (F02)."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..agent.context import Services
from ..categories import UNSUPPORTED, default_pack, pack_for
from ..errors import NotFound, ValidationFailed
from ..qloo.client import Trace
from ..schemas import (
    BrandCreated,
    BrandIn,
    BrandOut,
    BrandPatch,
    EntitiesIn,
    EntityOut,
    IntakeIn,
    ProductOut,
    ResolutionOut,
)
from ..security import workspace_id
from ..services.intake import propose
from ..services.resolve import resolve_product, validate_entity
from .deps import as_uuid, rate, svc

router = APIRouter(prefix="/v1")
log = logging.getLogger("stockist.brands")


@router.post("/brands/intake")
async def intake(body: IntakeIn, request: Request, _: str = Depends(workspace_id), s: Services = Depends(svc)) -> dict[str, Any]:
    if not body.website_url and not body.description:
        raise ValidationFailed("Give a website or a short description.")
    rate(request, "intake", 20, 3600)
    return await propose(s, str(body.website_url) if body.website_url else None, body.description)


async def _brand(s: Services, ws: str, brand_id: str) -> dict[str, Any]:
    b = await s.pool.fetchrow("select * from brands where id = $1 and workspace_id = $2", as_uuid(brand_id), uuid.UUID(ws))
    if b is None:
        raise NotFound("Brand not found")
    return dict(b)


async def _brand_out(s: Services, b: dict[str, Any]) -> BrandOut:
    prods = await s.pool.fetch("select * from products where brand_id = $1 order by position", b["id"])
    return BrandOut(
        id=str(b["id"]), name=b["name"], website_url=b["website_url"], category=b["category"], profile=b["profile"],
        unsupported_override=b["unsupported_override"],
        products=[ProductOut(id=str(p["id"]), name=p["name"], kind=p["kind"], notes=p["notes"],
                             entities=[EntityOut(**e) for e in p["entities"]] if p["entities"] else None) for p in prods],
    )


async def _replace_products(con: Any, ws: str, brand_id: uuid.UUID, products: list[Any]) -> list[str]:
    await con.execute("delete from products where brand_id = $1", brand_id)
    ids = []
    for i, p in enumerate(products):
        ids.append(str(await con.fetchval(
            "insert into products (workspace_id, brand_id, name, kind, notes, position) values ($1,$2,$3,$4,$5,$6) returning id",
            uuid.UUID(ws), brand_id, p.name, p.kind, p.notes, i)))
    return ids


@router.post("/brands", response_model=BrandCreated, status_code=201)
async def create_brand(body: BrandIn, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> BrandCreated:
    profile = body.profile.model_dump()
    category = body.profile.category
    if body.unsupported_override and (category == UNSUPPORTED or not body.profile.prospects_are_consumer_facing):
        log.info("unsupported override confirmed for workspace %s", ws)  # INT-04: logged
        category = default_pack().id if category == UNSUPPORTED else category
    async with s.pool.acquire() as con, con.transaction():
        bid = await con.fetchval(
            "insert into brands (workspace_id, name, website_url, category, profile, unsupported_override, source_text, "
            "source_text_expires_at, confirmed_at) values ($1,$2,$3,$4,$5,$6,$7,$8, now()) returning id",
            uuid.UUID(ws), body.name, str(body.website_url) if body.website_url else None, category, profile,
            body.unsupported_override, body.source_text, datetime.now(UTC) + timedelta(days=30) if body.source_text else None,
        )
        pids = await _replace_products(con, ws, bid, body.products)
    return BrandCreated(brand_id=str(bid), product_ids=pids)


@router.get("/brands/{brand_id}", response_model=BrandOut)
async def get_brand(brand_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> BrandOut:
    return await _brand_out(s, await _brand(s, ws, brand_id))


@router.patch("/brands/{brand_id}", response_model=BrandOut)
async def patch_brand(brand_id: str, body: BrandPatch, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> BrandOut:
    b = await _brand(s, ws, brand_id)
    async with s.pool.acquire() as con, con.transaction():
        if body.name is not None:
            await con.execute("update brands set name = $2 where id = $1", b["id"], body.name)
        if body.profile is not None:
            await con.execute("update brands set profile = $2, category = $3 where id = $1", b["id"],
                              body.profile.model_dump(), body.profile.category)
        if body.unsupported_override is not None:
            await con.execute("update brands set unsupported_override = $2 where id = $1", b["id"], body.unsupported_override)
        if body.products is not None:
            await _replace_products(con, ws, b["id"], body.products)
    return await _brand_out(s, await _brand(s, ws, brand_id))


@router.post("/brands/{brand_id}/resolve", response_model=list[ResolutionOut])
async def resolve(brand_id: str, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[ResolutionOut]:
    b = await _brand(s, ws, brand_id)
    pack = pack_for(b["category"])
    out = []
    for p in await s.pool.fetch("select * from products where brand_id = $1 order by position", b["id"]):
        res = await resolve_product(s, b, dict(p), pack, Trace(step="resolve_preview"))
        await s.pool.execute("update products set entities = $2 where id = $1", p["id"], res["entities"])
        out.append(ResolutionOut(**res))
    return out


@router.put("/products/{product_id}/entities", response_model=list[EntityOut])
async def set_entities(product_id: str, body: EntitiesIn, ws: str = Depends(workspace_id), s: Services = Depends(svc)) -> list[EntityOut]:
    p = await s.pool.fetchrow("select * from products where id = $1 and workspace_id = $2", as_uuid(product_id), uuid.UUID(ws))
    if p is None:
        raise NotFound("Product not found")
    current = {e["entity_id"]: e for e in (p["entities"] or [])}
    out = []
    for ref in body.entities:
        out.append(current.get(ref.entity_id) or await validate_entity(s, ref.entity_id, ref.source_call_id))
    await s.pool.execute("update products set entities = $2 where id = $1", p["id"], out)
    return [EntityOut(**e) for e in out]
