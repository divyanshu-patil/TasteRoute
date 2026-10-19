"""QLO-04, RNK-03, QLO-05, compaction."""

import json
from pathlib import Path

import pytest

from stockist_api.errors import QlooContractViolation
from stockist_api.qloo.client import TokenBucket, cache_key
from stockist_api.qloo.compact import compact_entity, tag_kind
from stockist_api.qloo.guards import guard_places, in_bbox
from stockist_api.qloo.models import InsightsBody, Place

FIX = Path(__file__).parents[1] / "fixtures" / "qloo"
BBOX = [40.5503390, -74.0566880, 40.7394340, -73.8329450]
CAFE = ["urn:tag:category:place:coffee_shop"]


def places(name: str) -> list[Place]:
    return InsightsBody.model_validate(json.loads((FIX / name).read_text())["body"]).results.entities


def test_recorded_fixtures_parse_and_pass_guards():
    ps = places("insights_bk_coffee_specialty_explain.json")
    assert len(ps) == 50 and all(p.affinity is not None for p in ps)
    assert all(p.explain() for p in ps)
    g = guard_places(ps, required_tags=CAFE, bbox=BBOX)
    assert len(g.kept) == 50 and not g.warnings


def test_guard_drops_outside_city_and_wrong_type():
    ps = places("insights_bk_coffee_baseline_strict.json")[:10]
    moved = [p.model_copy(update={"location": p.location.model_copy(update={"lat": 51.5, "lon": -0.12})}) for p in ps[:4]]
    wrong = [p.model_copy(update={"subtype": "urn:entity:brand"}) for p in ps[4:5]]
    g = guard_places(moved + wrong + ps[5:], required_tags=CAFE, bbox=BBOX)
    assert g.dropped == {"outside_city": 4, "wrong_type": 1} and len(g.kept) == 5
    assert g.warnings  # > 30% dropped
    with pytest.raises(QlooContractViolation):
        guard_places(wrong, required_tags=CAFE, bbox=BBOX)


def test_in_bbox_tolerance():
    assert in_bbox(40.56, -74.0, BBOX) and not in_bbox(40.0, -74.0, BBOX)


def test_cache_key_ignores_param_order():
    assert cache_key("/v2/insights", [("a", "1"), ("b", "2")]) == cache_key("/v2/insights", [("b", "2"), ("a", "1")])
    assert cache_key("/v2/insights", [("a", "1")]) != cache_key("/search", [("a", "1")])


async def test_token_bucket_spaces_calls_with_fake_clock():
    """QLO-05: never more than `rate` acquisitions per second."""
    now = [0.0]
    stamps = []

    async def sleep(s: float) -> None:
        now[0] += s

    b = TokenBucket(4.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(9):
        await b.acquire()
        stamps.append(now[0])
    assert all(b - a >= 0.25 - 1e-9 for a, b in zip(stamps, stamps[1:], strict=False))
    assert stamps[-1] == pytest.approx(2.0)


def test_compaction_keeps_taste_tags_only():
    raw = {"entity_id": "x", "name": "Cafe", "subtype": "urn:entity:place", "popularity": 0.5,
           "tags": [{"id": "urn:tag:customer_identity:qloo:locals", "name": "Locals", "type": "urn:tag:customer_identity:qloo"},
                    {"id": "urn:tag:hours:qloo:open_late", "name": "Open late", "type": "urn:tag:hours:qloo"}],
           "properties": {"website": "https://x.test", "images": [1, 2, 3]}}
    out = compact_entity(raw)
    assert [t["id"] for t in out["tags"]] == ["urn:tag:customer_identity:qloo:locals"]
    assert "images" not in out["properties"] and out["properties"]["website"] == "https://x.test"
    assert tag_kind("urn:tag:customer_identity:qloo:locals") == "customer_identity"
