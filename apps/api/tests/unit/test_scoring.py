"""RNK-02, RNK-04, RNK-05, RNK-06, FIT-02, ENT-03."""

import pytest

from stockist_api.scoring import names, rank
from stockist_api.scoring.fit import best_product
from stockist_api.scoring.reasons import distinctive, reason


def test_percentiles_ties_share_the_better_rank():
    assert rank.percentiles({"a": 3, "b": 2, "c": 2, "d": 1}) == {"a": 1.0, "b": 0.75, "c": 0.75, "d": 0.25}
    assert rank.percentiles({}) == {}


def test_lift_reorders_raw_target_order():
    # 'mainstream' has the top affinity but is also the most popular; 'niche' over-indexes.
    fillers = [rank.Candidate(f"f{i}", 0.1 * i, 0.5, 0) for i in range(1, 9)]
    target = [rank.Candidate("mainstream", 0.95, 0.99, 3), rank.Candidate("niche", 0.90, 0.01, 3), *fillers]
    out = {s.venue_id: s for s in rank.score_type("cafe", target, ["mainstream", "x"], {"x": 0.8, "mainstream": 0.99})}
    assert out["mainstream"].target_pct > out["niche"].target_pct
    assert out["niche"].lift > out["mainstream"].lift
    assert out["niche"].fit == rank.fit(out["niche"].target_pct, out["niche"].lift)
    merged = rank.merge([list(out.values())], 10)
    assert merged[0].venue_id == "niche" and [s.rank for s in merged] == list(range(1, 11))
    assert out["niche"].flags == ["not_in_baseline"] and out["mainstream"].flags == []


def test_fit_formula_ignores_negative_lift():
    assert rank.fit(0.8, 0.2) == round(0.7 * 0.8 + 0.3 * 0.2, 4)
    assert rank.fit(0.8, -0.5) == round(0.7 * 0.8, 4)


@pytest.mark.parametrize(("t", "lift", "support", "label"), [
    (0.8, 0.15, 2, "high"), (0.8, 0.15, 1, "medium"), (0.79, 0.5, 3, "medium"),
    (0.6, 0.05, 0, "medium"), (0.6, 0.049, 0, "low"), (0.59, 0.5, 5, "low"),
])
def test_confidence_boundaries(t, lift, support, label):
    assert rank.confidence(t, lift, support) == label


def test_support_counts_fair_share_contributors():
    assert rank.support([("a", 0.5), ("b", 0.3), ("c", 0.2)]) == 3
    assert rank.support([("a", 0.9), ("b", 0.05), ("c", 0.05)]) == 1
    assert rank.support([]) == 0


def test_merge_dedupes_and_caps():
    a = [rank.Scored("v1", "cafe", 0.9, 0.1, 0.8, 0.87, "high"), rank.Scored("v2", "cafe", 0.5, 0.5, 0, 0.35, "low")]
    b = [rank.Scored("v1", "bar", 0.5, 0.1, 0.4, 0.47, "low")]
    out = rank.merge([a, b], 1)
    assert len(out) == 1 and out[0].venue_type == "cafe"


def test_coverage_warnings():
    assert rank.coverage_warnings(40, {"cafe": 40}) == []
    w = rank.coverage_warnings(10, {"cafe": 10, "bar": 30})
    assert len(w) == 2 and "cafe" in w[1] and "bar" not in w[1]


def test_best_product_labels():
    assert best_product({}).label == "unscored"
    assert best_product({"a": 0.7}).label == "single_product"
    assert best_product({"a": 0.9, "b": 0.75}).label == "clear"
    assert best_product({"a": 0.9, "b": 0.85}).label == "close"
    f = best_product({"a": 0.9, "b": 0.89})
    assert f.label == "tie" and f.best == "a" and f.runner_up == "b"


@pytest.mark.parametrize(("q", "c", "ok"), [
    ("Blue Bottle", "Blue Bottle Coffee", True), ("GT's Kombucha", "GTs Kombucha", True),
    ("La Colombe", "La Colombe Coffee Roasters", True), ("Fernet Branca", "Fernet-Branca", True),
    ("Partners Coffee", "Waitrose & Partners", False), ("Kings County Distillery", "Sacramento Kings", False),
    ("Sey Coffee", "Starbucks", False),
    ("Health-Ade", "Health", False), ("Fieldnote Coffee", "Fieldnote", True),  # found in the live seed
])
def test_name_matching(q, c, ok):
    assert names.is_match(q, c) is ok


def test_reasons_skip_sensitive_and_common_tags():
    d = distinctive({"v1": ["Restaurant", "Natural wine"], "v2": ["Restaurant"], "v3": ["Restaurant", "Bakery"]})
    assert d == {"v1": ["Natural wine"], "v2": [], "v3": ["Bakery"]}
    text = reason(audience_overlap=["Natural wine"], crowd=["LGBTQ+ friendly", "Locals"], interests=["Specialty coffee"],
                  driver_names=["Blue Bottle Coffee"], best_product="Cold Brew", runner_up="Espresso", label="close")
    assert "lgbt" not in text.lower() and "(our inference)" in text and "(Qloo)" in text
