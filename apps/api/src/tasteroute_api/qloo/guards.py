"""Silent-failure guards run on every Qloo place response (QLO-04, RNK-03)."""

from dataclasses import dataclass, field

from ..errors import QlooContractViolation
from .models import Place

PLACE = "urn:entity:place"


@dataclass
class GuardResult:
    kept: list[Place]
    dropped: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def in_bbox(lat: float, lon: float, bbox: list[float], tolerance: float = 0.1) -> bool:
    """bbox = [south, west, north, east]; expanded by `tolerance` of its size on each side."""
    s, w, n, e = bbox
    dlat, dlon = (n - s) * tolerance, (e - w) * tolerance
    return s - dlat <= lat <= n + dlat and w - dlon <= lon <= e + dlon


def guard_places(places: list[Place], *, required_tags: list[str] | None, bbox: list[float] | None) -> GuardResult:
    out = GuardResult(kept=[])
    for p in places:
        if p.subtype and p.subtype != PLACE:
            reason = "wrong_type"
        elif bbox and p.location and not in_bbox(p.location.lat, p.location.lon, bbox):
            reason = "outside_city"
        elif required_tags and p.tags and not any(t.id in required_tags for t in p.tags):
            reason = "missing_tag"
        else:
            out.kept.append(p)
            continue
        out.dropped[reason] = out.dropped.get(reason, 0) + 1
    total = len(places)
    bad = total - len(out.kept)
    if total and bad == total:
        raise QlooContractViolation(f"Every returned entity failed the guard: {out.dropped}")
    if total and bad / total > 0.3:
        out.warnings.append(f"Guard dropped {bad} of {total} results ({out.dropped})")
    return out
