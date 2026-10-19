"""Shrink Qloo responses to the fields TasteRoute uses (a raw place response is ~2 MB).

Stored responses and fixtures both go through this, so the models only ever see compact data.
"""

from typing import Any

# Tag kinds that describe taste or the crowd; everything else (payments, parking, ...) is dropped.
# Brand entities (from /search) mostly carry genre and wikipedia tags, kept for display only.
TASTE_TAG_KINDS = {
    "category",
    "genre",
    "menu_highlight",
    "beverage_offering",
    "customer_identity",
    "interests",
    "ambience",
    "culinary_style",
    "cuisine",
    "specialty_dish",
    "setting",
    "decor",
    "visit_intent",
    "age_range",
    "neighborhood_characteristic",
}
PLACE_PROPS = (
    "address",
    "website",
    "phone",
    "neighborhood",
    "price_level",
    "business_rating",
    "short_description",
    "customer_demographics_description",
    "is_closed",
)


def tag_kind(tag_id_or_type: str) -> str:
    """'urn:tag:menu_highlight:qloo:cold_brew' -> 'menu_highlight'."""
    parts = tag_id_or_type.split(":")
    return parts[2] if len(parts) > 2 else ""


def compact_entity(e: dict[str, Any]) -> dict[str, Any]:
    props = e.get("properties") or {}
    out: dict[str, Any] = {
        "entity_id": e.get("entity_id"),
        "name": e.get("name"),
        "type": e.get("type"),
        "subtype": e.get("subtype"),
        "types": e.get("types"),
        "popularity": e.get("popularity"),
        "location": {k: v for k, v in (e.get("location") or {}).items() if k in ("lat", "lon")} or None,
        "query": e.get("query"),
        "tags": [
            {"id": t.get("id") or t.get("tag_id"), "name": t.get("name")}
            for t in e.get("tags") or []
            if tag_kind(t.get("type") or t.get("id") or t.get("tag_id") or "") in TASTE_TAG_KINDS
        ],
        "properties": {k: props[k] for k in PLACE_PROPS if props.get(k) is not None},
    }
    geo = props.get("geocode") or {}
    if geo:
        out["properties"]["geocode"] = {k: geo.get(k) for k in ("city", "name", "country_code") if geo.get(k)}
    if props.get("keywords"):
        out["properties"]["keywords"] = [k["name"] for k in props["keywords"][:8] if isinstance(k, dict)]
    if props.get("official_site"):
        out["properties"]["official_site"] = props["official_site"]
    return {k: v for k, v in out.items() if v is not None}


def compact_response(body: Any) -> Any:
    """Compact /search, /v2/insights (entities or tags) and /v2/tags bodies; pass anything else through."""
    if not isinstance(body, dict):
        return body
    out = dict(body)
    if isinstance(body.get("results"), list):  # /search
        out["results"] = [compact_entity(e) for e in body["results"]]
    elif isinstance(body.get("results"), dict):
        res = dict(body["results"])
        if isinstance(res.get("entities"), list):
            res["entities"] = [compact_entity(e) for e in res["entities"]]
        if isinstance(res.get("tags"), list):
            res["tags"] = [
                {k: t.get(k) for k in ("id", "name", "type", "subtype", "tag_id", "query", "popularity") if k in t}
                for t in res["tags"]
            ]
        out["results"] = res
    return out
