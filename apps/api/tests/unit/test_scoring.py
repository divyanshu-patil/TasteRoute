"""RNK-02, RNK-04, RNK-05, RNK-06, FIT-02, ENT-03."""

import pytest

from tasteroute_api.scoring import names, rank
from tasteroute_api.scoring.fit import best_product, zscores
from tasteroute_api.scoring.reasons import distinctive, plain_tags, reason


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


def test_lift_against_mass_market_taste_at_the_same_venues():
    """RNK-07 (D-23): 'everyone' is top for the brand and for Coca-Cola alike; 'yours' is top only for the brand. The
    generic reading changes the order; a venue Qloo gives no generic reading counts as the lowest and is flagged."""
    fillers = [rank.Candidate(f"f{i}", 0.1 * i, 0.5, 0) for i in range(1, 9)]
    target = [rank.Candidate("everyone", 0.95, 0.99, 2), rank.Candidate("yours", 0.90, 0.20, 2), *fillers]
    generic = {"everyone": 0.97, "yours": 0.15, **{f"f{i}": 0.1 * i for i in range(1, 8)}}  # f8 missing
    out = {s.venue_id: s for s in rank.score_against_generic("cafe", target, generic)}
    assert out["everyone"].target_pct > out["yours"].target_pct
    assert rank.merge([list(out.values())], 10)[0].venue_id == "yours"
    assert out["yours"].baseline_pct < out["everyone"].baseline_pct and out["yours"].popularity_pct is not None
    assert out["f8"].flags == ["generic_missing"] and out["f8"].baseline_pct == out["f1"].baseline_pct


def test_buyability_flags():
    """RNK-09: chains by repeat name or the pack list; a venue that is a brand in your signal; a maker of what you make;
    alcohol words in a product."""
    from tasteroute_api.categories import default_pack
    from tasteroute_api.scoring import buyability as b

    pack = default_pack().buyability
    places = {"1": "Joe Coffee Company", "2": "Joe Coffee Company", "3": "Starbucks Coffee", "4": "Sey Coffee",
              "5": "Blue Bottle Coffee"}
    assert b.chains(places, pack.chains) == {"1", "2", "3", "5"}
    assert b.own_brand("Sey Coffee", ["Sey Coffee Roasters", "Partners Coffee"]) and not b.own_brand("Devoción", ["Sey Coffee"])
    makers = [(m.kinds, m.tags) for m in pack.makers]
    assert b.maker({"urn:tag:category:place:coffee_roastery"}, "Cold Brew Concentrate coffee", makers)
    assert not b.maker({"urn:tag:category:place:coffee_roastery"}, "Aperitivo", makers)
    assert b.alcoholic("Bitter Aperitivo", pack.alcohol_keywords) and b.alcoholic("Sparkling wines", pack.alcohol_keywords)
    assert not b.alcoholic("Alexander's oat milk", pack.alcohol_keywords)


def test_hidden_venues_rank_after_shown_ones():
    rows = [rank.Scored("chain", "cafe", 0.9, 0.1, 0.8, 0.9, "high", ["chain"]),
            rank.Scored("local", "cafe", 0.5, 0.5, 0.0, 0.35, "low")]
    assert [s.venue_id for s in rank.merge([rows], 10, ("chain",))] == ["local", "chain"]


def test_fit_formula_ignores_negative_lift():
    assert rank.fit(0.8, 0.2) == round(0.7 * 0.8 + 0.3 * 0.2, 4)
    assert rank.fit(0.8, -0.5) == round(0.7 * 0.8, 4)


@pytest.mark.parametrize(("t", "lift", "support", "label"), [
    (0.8, 0.15, 2, "high"), (0.8, 0.15, 1, "medium"), (0.79, 0.5, 3, "medium"),
    (0.6, 0.05, 0, "medium"), (0.6, 0.049, 0, "low"), (0.59, 0.5, 5, "low"),
])
def test_confidence_boundaries(t, lift, support, label):
    assert rank.confidence(t, lift, support) == label


def test_one_brand_signal_can_be_high_confidence():
    assert rank.confidence(0.8, 0.15, 1, signals=1) == "high"
    assert rank.confidence(0.8, 0.15, 1, signals=3) == "medium"


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
    assert best_product({"a": 1.5, "b": 0.5}, {"a": 0.9, "b": 0.5}).label == "clear"
    assert best_product({"a": 1.5, "b": 0.5}, {"a": 0.5, "b": 0.5}).label == "close"  # z-gap, but no raw gap
    assert best_product({"a": 0.9, "b": 0.5}).label == "close"
    f = best_product({"a": 0.9, "b": 0.8})
    assert f.label == "tie" and f.best == "a" and f.runner_up == "b"


def test_best_product_by_standardised_affinity():
    """FIT-04: at an Oslo-like café the coffee product's affinity stands out among cafés and the amaro's barely does;
    percentiles alone said amaro (rank 1 of a flat band vs rank 2), z-scores say coffee."""
    coffee = {"oslo": 0.95, "v1": 0.96, **{f"c{i}": 0.40 + 0.02 * i for i in range(10)}}
    amaro = {"oslo": 0.31, "v1": 0.305, **{f"c{i}": 0.30 if i < 7 else 0.05 for i in range(10)}}
    pct = {"coffee": rank.percentiles(coffee)["oslo"], "amaro": rank.percentiles(amaro)["oslo"]}
    assert pct["amaro"] > pct["coffee"]
    z = {"coffee": zscores(coffee)["oslo"], "amaro": zscores(amaro)["oslo"]}
    f = best_product(z, {"coffee": coffee["oslo"], "amaro": amaro["oslo"]})
    assert f.best == "coffee" and f.label == "clear"


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
    assert "lgbt" not in text.lower() and text.count("(Qloo)") == 3
    with_music = reason(audience_overlap=[], crowd=[], interests=[], driver_names=[], best_product=None, runner_up=None,
                        label="unscored", music=["Sylvan Esso", "Rhye"])
    assert "Scores high with fans of Sylvan Esso and Rhye, music your brands' fans like (Qloo)." in with_music  # EVD-06


def test_reasons_never_list_the_venue_type_and_read_plainly():
    """EVD-05: 'Cafe' and 'Tourist attraction' say what the venue is, not why it fits; cuisines keep their capital."""
    from tasteroute_api.categories import default_pack

    pack = default_pack()
    drop = pack.reasons.drop + [v.label for v in pack.venue_types]
    tags = plain_tags(["Cafe", "Tourist attraction", "American", "Brunch"], drop)
    assert tags == ["American", "Brunch"]
    text = reason(audience_overlap=tags, crowd=[], interests=["Specialty coffee"], driver_names=["Sey Coffee"],
                  best_product="cold brew", runner_up=None, label="clear", phrases=pack.reasons.phrases)
    assert text.startswith("Known for American food and brunch, which fans of Sey Coffee over-index on (Qloo).")
    assert "Guests here are into specialty coffee (Qloo)." in text and "Lead with cold brew (Qloo)." in text
    assert "cafe" not in text.lower() and "over-index on cafe" not in text.lower()


def test_brand_extension_must_fit_the_product():
    pickle = "garlic dill pickles pickles small-batch"
    assert names.is_match("Grillo's", "Grillo's Pickles", pickle)
    assert not names.is_match("Bubbies", "Bubbies Ice Cream", pickle)
    assert names.is_match("Blue Bottle", "Blue Bottle Coffee", "nitro cold brew")  # generic word
    assert names.is_match("McClure's Pickles", "McClure's", pickle)  # the query may drop a word the product uses
    assert not names.is_match("Health-Ade", "Health", "ginger kombucha")
    assert names.is_match("Kaigo", "Kaigo Coffee Room")  # venues (no context) keep the old rule
