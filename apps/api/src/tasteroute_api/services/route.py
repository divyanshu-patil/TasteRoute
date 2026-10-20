"""Taste route (QLO-11): the top venues grouped into walkable areas, in a suggested visiting order for a rep's week.

Areas are ordered by Qloo's taste heatmap. Each heatmap cell (about 150 m) has an affinity rank for the brand signal
and one for the mass-market brands (D-23); their difference says where your brands' fans concentrate more than everyone's.
Ranking by fit stays the default and this never changes a score. Two Qloo calls per run; the mass-market heatmap is the
same for every brand in a city, so it is usually cached. Distances are straight lines."""

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from ..agent.context import Services
from ..agent.tools import qualified_city
from ..categories import pack_for
from ..external.osm import haversine_m
from ..qloo import api
from ..qloo.client import Trace
from ..scoring.buyability import HIDDEN

TOP = 15  # venues in the route
WALK_M = 1200  # a venue this close to an area's venue joins that area

Cell = tuple[float, float, float]  # lat, lon, lift (taste rank minus mass-market rank)


def _m(a: dict[str, Any], b: dict[str, Any]) -> float:
    return haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])


def inside(cells: dict[str, tuple[float, float, float]], box: list[float] | None) -> dict[str, tuple[float, float, float]]:
    return {g: c for g, c in cells.items() if not box or (box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3])}


def lift_cells(taste: dict[str, tuple[float, float, float]], mass: dict[str, tuple[float, float, float]]) -> list[Cell]:
    """Per heatmap cell both calls return: the brand signal's affinity rank minus the mass-market brands' (D-23)."""
    return [(lat, lon, t - mass[g][2]) for g, (lat, lon, t) in taste.items() if g in mass]


def lift_at(lat: float, lon: float, cells: list[Cell]) -> float:
    """The lift of the nearest cell."""
    return min(cells, key=lambda c: haversine_m(lat, lon, c[0], c[1]))[2]


def _walk(area: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nearest-neighbour order from the best-ranked venue."""
    path, left = [area[0]], area[1:]
    while left:
        nxt = min(left, key=lambda w: _m(path[-1], w))
        path.append(nxt)
        left.remove(nxt)
    return path


def plan(venues: list[dict[str, Any]], cells: list[Cell]) -> list[dict[str, Any]]:
    """venues in rank order (venue_id, name, rank, lat, lon, nb) -> areas in visiting order: the strongest taste
    hotspot first (mean heatmap lift at the area's venues), ties by best rank."""
    groups: list[list[dict[str, Any]]] = []
    for v in venues:  # single linkage: a venue joins (and merges) every area within walking distance
        near = [g for g in groups if any(_m(v, w) <= WALK_M for w in g)]
        groups = [g for g in groups if g not in near] + [sorted([v, *(w for g in near for w in g)], key=lambda w: w["rank"])]
    areas: list[dict[str, Any]] = []
    for g in groups:
        lift = sum(lift_at(w["lat"], w["lon"], cells) for w in g) / len(g) if cells else 0.0
        named = Counter(w["nb"] for w in g if w.get("nb")).most_common(1)
        stops = _walk(g)
        areas.append({
            "name": named[0][0] if named else f"Around {g[0]['name']}",
            "lift": round(lift * 100),  # percentile points, like a venue's lift
            "walk_km": round(sum(_m(a, b) for a, b in zip(stops, stops[1:], strict=False)) / 1000, 1),
            "stops": [{k: w[k] for k in ("venue_id", "name", "rank", "lat", "lon")} for w in stops],
        })
    areas.sort(key=lambda a: (-a["lift"], a["stops"][0]["rank"]))
    seen: set[str] = set()
    for a in areas:  # two areas in one neighbourhood: the stronger keeps its name
        if a["name"] in seen:
            a["name"] = f"Around {a['stops'][0]['name']}"
        seen.add(a["name"])
    return areas


async def taste_route(s: Services, run_id: str) -> dict[str, Any]:
    rid = uuid.UUID(run_id)
    run = await s.pool.fetchrow("select r.route, r.settings, r.city, b.category from runs r join brands b on b.id = r.brand_id "
                                "where r.id = $1", rid)
    if run["route"]:
        return dict(run["route"])
    venues = [dict(r) for r in await s.pool.fetch(
        "select vs.venue_id::text as venue_id, v.name, vs.rank, v.lat, v.lon, v.properties->>'neighborhood' as nb "
        "from venue_scores vs join venues v on v.id = vs.venue_id where vs.run_id = $1 and v.lat is not null "
        "and not (vs.flags && $2::text[]) order by vs.rank limit $3", rid, list(HIDDEN), TOP)]
    city, trace = run["city"], Trace(run_id=run_id, step="taste_route")
    box = city.get("bbox")

    async def heat(ids: list[str]) -> tuple[dict[str, tuple[float, float, float]], str]:
        q = city.get("qloo_query") or city["name"]
        cells, call = await api.heatmap(s.qloo, city_query=q, signal_ids=ids, trace=trace)
        alt = qualified_city(city)
        if cells and not inside(cells, box) and alt and alt != q:  # a bare name can land in another city (QLO-12)
            cells, call = await api.heatmap(s.qloo, city_query=alt, signal_ids=ids, trace=trace)
        return inside(cells, box), call

    taste, tcall = await heat([x["entity_id"] for x in (run["settings"] or {}).get("signal") or []])
    mass, mcall = await heat(pack_for(run["category"]).baseline_entities)
    cells = lift_cells(taste, mass)
    route = {
        "areas": plan(venues, cells),
        "heat": [[round(lat, 5), round(lon, 5), round(lift, 3)] for lat, lon, lift in cells if lift > 0],
        "source_call_ids": [tcall, mcall],
        "created_at": datetime.now(UTC).isoformat(),
    }
    await s.pool.execute("update runs set route = $2 where id = $1", rid, route)
    return route
