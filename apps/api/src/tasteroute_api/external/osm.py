"""Nominatim city and place lookup (1 req/s, cached 30 days) and Overpass venue contact tags (single-flight, cached 7 days)."""

import asyncio
import math
from datetime import timedelta
from typing import Any

import asyncpg
import httpx

from ..errors import AppError
from ..qloo.client import TokenBucket
from ..scoring.names import similarity
from . import Emit, cached_call

_nominatim_bucket: TokenBucket | None = None
_overpass_lock: asyncio.Lock | None = None


def _bucket() -> TokenBucket:
    global _nominatim_bucket
    if _nominatim_bucket is None:
        _nominatim_bucket = TokenBucket(1.0)
    return _nominatim_bucket


def _lock() -> asyncio.Lock:
    global _overpass_lock
    if _overpass_lock is None:
        _overpass_lock = asyncio.Lock()
    return _overpass_lock


# Address parts that read well to a person, most local first. Counties, districts and postcodes are left out.
_PLAIN_KEYS = ("road", "neighbourhood", "quarter", "suburb", "city", "town", "village", "state", "country")


def plain(x: dict[str, Any]) -> tuple[str, str]:
    """A Nominatim result as (label, detail) in plain English, e.g. ("Brooklyn", "New York, United States")."""
    a = x.get("address") or {}
    street = " ".join(str(a[k]) for k in ("house_number", "road") if a.get(k))
    label = x.get("name") or street or (x.get("display_name") or "").split(",")[0]
    parts: list[str] = []
    for k in _PLAIN_KEYS:
        v = a.get(k)
        if v and v != label and v not in parts and not (k == "road" and street == label):
            parts.append(str(v))
    return label, ", ".join(parts)


async def _nominatim(pool: asyncpg.Pool, http: httpx.AsyncClient, base_url: str, user_agent: str, path: str,
                     params: dict[str, Any], key: dict[str, Any]) -> Any:
    """One Nominatim request: 1 req/s, cached 30 days, English names. Only on an explicit user action (no autocomplete)."""
    async def fetch() -> tuple[int, Any]:
        await _bucket().acquire()
        try:
            r = await http.get(
                f"{base_url}{path}",
                params={**params, "format": "jsonv2", "addressdetails": 1, "accept-language": "en"},
                headers={"User-Agent": user_agent},
                timeout=15,
            )
        except httpx.HTTPError:
            return 503, None
        return r.status_code, r.json() if r.status_code == 200 else None

    status, body, _, _ = await cached_call(pool, "nominatim", path, key, timedelta(days=30), fetch)
    if status != 200:
        raise AppError("Location search is unavailable right now. Try again in a moment.", code="city_search_unavailable",
                       status=503)
    return body


async def search_cities(pool: asyncpg.Pool, http: httpx.AsyncClient, base_url: str, user_agent: str, q: str) -> list[dict[str, Any]]:
    body = await _nominatim(pool, http, base_url, user_agent, "/search", {"q": q, "limit": 5}, {"q": q.strip().lower()})
    if not isinstance(body, list):
        return []
    out = []
    for x in body:
        addr = x.get("address") or {}
        name = x.get("name") or (x.get("display_name") or "").split(",")[0]
        bb = [float(v) for v in x.get("boundingbox", [])]
        if len(bb) != 4:
            continue
        label, detail = plain(x)
        out.append({
            "id": f"{x.get('osm_type', 'n')[0]}{x.get('osm_id')}",
            "name": name,
            "display_name": x.get("display_name", name),
            "country": addr.get("country_code", "").upper(),
            "lat": float(x["lat"]),
            "lon": float(x["lon"]),
            "bbox": [bb[0], bb[2], bb[1], bb[3]],  # nominatim: [s, n, w, e] -> ours: [s, w, n, e]
            "label": label,
            "detail": detail,
        })
    return out


async def search_places(pool: asyncpg.Pool, http: httpx.AsyncClient, base_url: str, user_agent: str, q: str,
                        bbox: list[float] | None) -> list[dict[str, Any]]:
    """Addresses, businesses or neighbourhoods matching q, inside bbox [s, w, n, e] when given."""
    params: dict[str, Any] = {"q": q, "limit": 6}
    if bbox:
        s, w, n, e = bbox
        params |= {"viewbox": f"{w},{n},{e},{s}", "bounded": 1}
    body = await _nominatim(pool, http, base_url, user_agent, "/search", params,
                            {"place_q": q.strip().lower(), "bbox": [round(v, 3) for v in bbox] if bbox else None})
    out, seen = [], set()
    for x in body if isinstance(body, list) else []:
        label, detail = plain(x)
        if (label, detail) not in seen:  # a street comes back once per OSM segment; one suggestion is enough
            seen.add((label, detail))
            out.append({"label": label, "detail": detail, "lat": float(x["lat"]), "lon": float(x["lon"])})
    return out


async def reverse_place(pool: asyncpg.Pool, http: httpx.AsyncClient, base_url: str, user_agent: str,
                        lat: float, lon: float) -> dict[str, Any]:
    """The address at a map pin; a plain "Dropped pin" when Nominatim has none (open water, parks)."""
    lat, lon = round(lat, 5), round(lon, 5)
    body = await _nominatim(pool, http, base_url, user_agent, "/reverse", {"lat": lat, "lon": lon, "zoom": 18},
                            {"lat": lat, "lon": lon})
    if not isinstance(body, dict) or body.get("error") or "lat" not in body:
        return {"label": "Dropped pin", "detail": f"{lat:.4f}, {lon:.4f}", "lat": lat, "lon": lon}
    label, detail = plain(body)
    return {"label": label, "detail": detail, "lat": lat, "lon": lon}


def overpass_query(key: str, value: str, bbox: list[float]) -> str:
    s, w, n, e = bbox
    b = f"({s},{w},{n},{e})"
    sel = f'nwr["{key}"="{value}"]'
    return (
        f"[out:json][timeout:90];({sel}[\"website\"]{b};{sel}[\"contact:website\"]{b};"
        f"{sel}[\"email\"]{b};{sel}[\"contact:email\"]{b};);out center tags;"
    )


async def venue_tags(
    pool: asyncpg.Pool,
    http: httpx.AsyncClient,
    base_url: str,
    user_agent: str,
    *,
    key: str,
    value: str,
    bbox: list[float],
    run_id: str | None = None,
    emit: Emit | None = None,
    sleep: Any = asyncio.sleep,
) -> tuple[list[dict[str, Any]], str | None]:
    q = overpass_query(key, value, bbox)

    async def fetch() -> tuple[int, Any]:
        async with _lock():  # never parallel
            for attempt in range(2):
                try:
                    r = await http.post(base_url, data={"data": q}, headers={"User-Agent": user_agent}, timeout=100)
                except httpx.HTTPError:
                    return 504, None
                if r.status_code in (429, 406, 504) and attempt == 0:
                    await sleep(30)
                    continue
                if r.status_code != 200:
                    return r.status_code, None
                els = r.json().get("elements", [])
                keep = ("name", "website", "contact:website", "email", "contact:email", "phone", "contact:phone")
                return 200, [
                    {
                        "id": f"{e.get('type')}/{e.get('id')}",
                        "lat": e.get("lat") or (e.get("center") or {}).get("lat"),
                        "lon": e.get("lon") or (e.get("center") or {}).get("lon"),
                        "tags": {k: v for k, v in (e.get("tags") or {}).items() if k in keep},
                    }
                    for e in els
                ]
            return 429, None

    params = {"key": key, "value": value, "bbox": [round(v, 4) for v in bbox]}
    status, body, call_id, _ = await cached_call(
        pool, "overpass", "/interpreter", params, timedelta(days=7), fetch, run_id=run_id, emit=emit
    )
    return (body if status == 200 and isinstance(body, list) else []), call_id


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = math.radians
    a = math.sin(r(lat2 - lat1) / 2) ** 2 + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def match_osm(name: str, lat: float | None, lon: float | None, elements: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Name similarity ≥ 0.85 and distance ≤ 150 m (CON-01)."""
    if lat is None or lon is None:
        return None
    best, best_sim = None, 0.0
    for e in elements:
        if e.get("lat") is None or e.get("lon") is None:
            continue
        sim = similarity(name, e["tags"].get("name", ""))
        if sim >= 0.85 and sim > best_sim and haversine_m(lat, lon, e["lat"], e["lon"]) <= 150:
            best, best_sim = e, sim
    return best
