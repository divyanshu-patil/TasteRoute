"""Nominatim city lookup (1 req/s, cached 30 days) and Overpass venue contact tags (single-flight, cached 7 days)."""

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


async def search_cities(pool: asyncpg.Pool, http: httpx.AsyncClient, base_url: str, user_agent: str, q: str) -> list[dict[str, Any]]:
    async def fetch() -> tuple[int, Any]:
        await _bucket().acquire()
        try:
            r = await http.get(
                f"{base_url}/search",
                params={"q": q, "format": "jsonv2", "limit": 5, "addressdetails": 1},
                headers={"User-Agent": user_agent},
                timeout=15,
            )
        except httpx.HTTPError:
            return 503, None
        return r.status_code, r.json() if r.status_code == 200 else None

    status, body, _, _ = await cached_call(pool, "nominatim", "/search", {"q": q.strip().lower()}, timedelta(days=30), fetch)
    if status != 200:
        raise AppError("City search is unavailable right now. Try again in a moment.", code="city_search_unavailable",
                       status=503)
    if not isinstance(body, list):
        return []
    out = []
    for x in body:
        addr = x.get("address") or {}
        name = x.get("name") or (x.get("display_name") or "").split(",")[0]
        bb = [float(v) for v in x.get("boundingbox", [])]
        if len(bb) != 4:
            continue
        out.append({
            "id": f"{x.get('osm_type', 'n')[0]}{x.get('osm_id')}",
            "name": name,
            "display_name": x.get("display_name", name),
            "country": addr.get("country_code", "").upper(),
            "lat": float(x["lat"]),
            "lon": float(x["lon"]),
            "bbox": [bb[0], bb[2], bb[1], bb[3]],  # nominatim: [s, n, w, e] -> ours: [s, w, n, e]
        })
    return out


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
