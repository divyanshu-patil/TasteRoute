"""DRF-02..05, EXP-01, EXP-02, CON-02, CON-03, CON-07, AGT-01."""

import csv
import io
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from tasteroute_api.agent import rules
from tasteroute_api.agent.plan_guard import PlanGuard
from tasteroute_api.agent.tools import qualified_city
from tasteroute_api.categories import default_pack
from tasteroute_api.errors import AppError
from tasteroute_api.external import hunter
from tasteroute_api.grounding import Bundle, validate
from tasteroute_api.services.contacts import (
    Candidate,
    choose,
    is_suppressed,
    names_venue,
    venue_addresses,
    venue_inbox,
)
from tasteroute_api.services.drafts import kind_unless_named, next_status, short_name, template_draft
from tasteroute_api.services.export import CSV_COLUMNS, MAILTO_BODY_MAX, mailto, mask, to_csv

OPT_OUT = "If you'd rather not hear from me, reply 'no thanks' and I won't contact you again."


def bundle(**kw) -> Bundle:
    base = dict(
        venue_name="Oslo Coffee Roasters", venue_type="Cafés", brand_name="Fieldnote Coffee", sender_name="Mara",
        product_names=["Cold Brew Concentrate", "House Espresso"], best_product="Cold Brew Concentrate",
        reason="Guests here over-index on espresso bar (Qloo).",
        evidence={"e1": "Known for Espresso bar, Specialty coffee, which fans of your brands over-index on",
                  "e2": "Fans of Blue Bottle Coffee like this venue"},
        evidence_values={"e1": ["Espresso bar", "Specialty coffee"], "e2": ["Blue Bottle Coffee"]},
        forbidden_claims=default_pack().pitch_style.forbidden_claims,
        contact_role=None, ask_examples=["send a free sample", "drop by for a 10-minute tasting"], opt_out_line=OPT_OUT,
    )
    return Bundle(**{**base, **kw})


GOOD = (f"Hi Oslo Coffee Roasters team,\n\nI'm Mara from Fieldnote Coffee. Your guests over-index on espresso bar and "
        f"specialty coffee. I think Cold Brew Concentrate would suit you. Could I drop by for a 10-minute tasting?\n\nMara\n\n{OPT_OUT}")


def test_validator_accepts_grounded_draft():
    assert validate("Cold Brew Concentrate for Oslo Coffee Roasters", GOOD, ["e1"], bundle()) == []


def test_kind_left_out_when_the_name_says_it():
    assert kind_unless_named("Nitro Cold Brew", "cold brew coffee") == ""
    assert kind_unless_named("Ginger Kombucha", "kombucha") == ""
    assert kind_unless_named("House Espresso", "coffee beans") == "coffee beans"


def test_validator_accepts_a_brand_name_ending_in_a_period():
    body = GOOD.replace("Fieldnote Coffee.", "Fieldnote Drinks Co., we make cold brew.")
    assert validate("Cold Brew Concentrate", body, ["e1"], bundle(brand_name="Fieldnote Drinks Co.")) == []


@pytest.mark.parametrize(("subject", "body", "ids", "needle"), [
    ("Hi", GOOD.replace("Mara from", "Mara from Starbucks and"), ["e1"], "Starbucks"),  # invented name
    ("Hi", GOOD.replace("10-minute", "25-minute"), ["e1"], "number"),  # invented number
    ("Hi", GOOD, ["e9"], "unknown evidence"),  # evidence id from another venue
    ("Hi", GOOD, [], "cite"),
    ("Hi", GOOD.replace(OPT_OUT, ""), ["e1"], "opt-out"),
    ("Hi", GOOD.replace("Oslo Coffee Roasters", "there"), ["e1"], "venue"),
    ("x" * 81, GOOD, ["e1"], "subject"),
    ("Hi", GOOD + "a" * 900, ["e1"], "body"),
])
def test_validator_rejects(subject, body, ids, needle):
    errors = validate(subject, body, ids, bundle())
    assert any(needle.lower() in e.lower() for e in errors), errors


@pytest.mark.parametrize("sentence", [
    "4 cafés nearby already stock our kombucha and it sold out at whole foods in 9 days.",
    "Qloo taste data shows your guests over-index heavily on natural wine and oat milk lattes.",
    "We'll give you half off your first order and free samples forever.",
    "We're award-winning, certified organic, best in the city.",
])
def test_validator_rejects_ungrounded_claims(sentence):
    """DRF-08: each of these passed the old validator."""
    body = GOOD.replace("I think Cold Brew Concentrate would suit you.", sentence + " I think Cold Brew Concentrate would suit you.")
    assert validate("Cold Brew Concentrate for Oslo Coffee Roasters", body, ["e1"], bundle())


def test_validator_numbers_are_whole_tokens_and_names_may_hold_claim_words():
    """DRF-08: '4' isn't allowed by '94'; a venue called 'Best Pizza' and the pack's 'free sample' ask are fine."""
    b = bundle(evidence={**bundle().evidence, "e3": "Popularity 94"})
    assert any("number" in e for e in validate("Hi", GOOD.replace("Mara from", "Mara (4 years) from"), ["e1"], b))
    good = GOOD.replace("Oslo Coffee Roasters", "Best Pizza").replace("drop by for a 10-minute tasting", "send a free sample")
    assert validate("Hi", good + "\n\nBest,\nMara", ["e1"], bundle(venue_name="Best Pizza")) == []
    taste = GOOD.replace("Your guests over-index on espresso bar and specialty coffee.", "Your guests love what we do.")
    assert any("unsupported_taste_claim" in e for e in validate("Hi", taste, ["e1"], bundle()))


def test_template_always_passes_validator():
    for ev, values in (({}, {}), ({"e1": "Crowd: Locals. Interests: Specialty coffee"}, {"e1": ["Specialty coffee", "Locals"]}),
                       (bundle().evidence, bundle().evidence_values), ({"e2": "Fans of Blue Bottle Coffee like this venue"},
                                                                         {"e2": ["Blue Bottle Coffee"]})):
        for address in ("", "12 Main St, Brooklyn, NY 11201"):
            b = bundle(evidence=ev or {"x": "Qloo taste fit and popularity baseline"}, evidence_values=values,
                       postal_address=address)
            t = template_draft(b)
            assert OPT_OUT in t.body and address in t.body  # DRF-05, DRF-09
            assert validate(t.subject, t.body, t.cited_evidence_ids, b) == [], t.body


def test_team_name_is_not_doubled():
    from tasteroute_api.services.drafts import team_name

    assert team_name("Fieldnote") == "The Fieldnote team" and team_name("The Finnish Long Drink") == "The Finnish Long Drink team"


def test_short_name():
    assert short_name("White Noise Coffee - Coffee Shop & Roastery") == "White Noise Coffee"
    assert short_name("Café Grumpy") == "Café Grumpy"


def test_state_machine():
    assert next_status("draft", edited=True, approve=False) == "edited"
    assert next_status("draft", edited=False, approve=True) == "approved"
    assert next_status("approved", edited=True, approve=False) == "edited"
    assert next_status("exported", edited=True, approve=False) == "edited"
    assert next_status("approved", edited=False, approve=False, export=True) == "exported"
    with pytest.raises(AppError):
        next_status("edited", edited=False, approve=False, export=True)


def test_mailto_encoding_and_cap():
    m = mailto("hello@cafe.test", "Cold brew & you", "Line one\nLine two: 100% fun?")
    u = urlparse(m)
    q = parse_qs(u.query)
    assert u.scheme == "mailto" and unquote(u.path) == "hello@cafe.test"
    assert q["subject"] == ["Cold brew & you"] and q["body"] == ["Line one\nLine two: 100% fun?"]
    long = mailto("a@b.test", "s", "word " * 2000)
    assert len(long.split("body=")[1]) <= MAILTO_BODY_MAX and "Shortened" in unquote(long)


def test_csv_columns_escaping_utf8():
    text = to_csv([{"rank": 1, "venue_name": 'Café "Grumpy", Greenpoint', "draft_body": "a\nb", "fit": None}])
    rows = list(csv.DictReader(io.StringIO(text)))
    assert list(rows[0]) == CSV_COLUMNS
    assert rows[0]["venue_name"] == 'Café "Grumpy", Greenpoint' and rows[0]["draft_body"] == "a\nb" and rows[0]["fit"] == ""


def test_mask():
    assert mask("hello@cafe.test") == "h***@cafe.test"


def test_contact_choice_order():
    c = choose([
        Candidate("x@v.test", "hunter", "personal", None, 90, "accept_all"),
        Candidate("web@v.test", "website", "generic"),
        Candidate("osm@v.test", "osm", "generic"),
        Candidate("bad@v.test", "hunter", "generic", "owner", 99, "invalid"),
        Candidate("role@v.test", "hunter", "personal", "Owner", 80, "valid"),
    ])
    assert c and c.email == "role@v.test"
    assert choose([Candidate("web@v.test", "website", "generic"), Candidate("osm@v.test", "osm", "generic")]).email == "osm@v.test"
    assert choose([Candidate("bad@v.test", "hunter", "generic", None, 99, "invalid")]) is None


def test_contact_choice_prefers_pitch_inbox_on_venue_domain():
    site = [Candidate("reservations@v.test", "website", "generic"), Candidate("hi@agency.test", "website", "generic"),
            Candidate("info@v.test", "website", "generic"), Candidate("sales@v.test", "website", "generic")]
    assert choose(site, "v.test").email == "sales@v.test"
    assert choose(site[:3], "v.test").email == "info@v.test"
    assert choose(site[:2], "v.test").email == "reservations@v.test"  # on-domain beats another site's address


def test_hunter_only_gets_venue_domains():
    assert hunter.registrable_domain("https://www.oslocoffee.com/menu") == "oslocoffee.com"
    for url in ("https://instagram.com/oslo", "https://www.facebook.com/x", "https://linktr.ee/x", "https://x.square.site"):
        assert hunter.skip_domain(hunter.registrable_domain(url)), url
    assert not hunter.skip_domain("oslocoffee.com")


def test_suppression_matches_subdomains():
    assert is_suppressed("a@shop.cafe.test", set(), {"cafe.test"})
    assert is_suppressed("A@Cafe.test", {"a@cafe.test"}, set())
    assert not is_suppressed("a@notcafe.test", set(), {"cafe.test"})


def test_plan_guard():
    """AGT-08: safety, not a script. Known ids only (a subset is the agent's choice), order, caps, no repeats."""
    g = PlanGuard("scout", {"product_ids": {"p1", "p2"}, "venue_types": {"cafe"}, "pack_types": {"cafe", "bar", "deli"}})
    assert "Unknown tool" in g.check("send_email", {})[1]
    assert "before" in g.check("rank_venues", {})[1]
    assert "subset" in g.check("resolve_entities", {"product_ids": ["p1", "zzz"]})[1]
    assert "Invalid arguments" in g.check("resolve_entities", {"oops": 1})[1]
    args, err = g.check("resolve_entities", {"product_ids": ["p2", "p1"]})
    assert err is None
    g.record("resolve_entities", args)
    assert "already called" in g.check("resolve_entities", {"product_ids": ["p2", "p1"]})[1]
    assert "must be one of" in g.check("suggest_more_comparables", {"product_id": "invented", "reason": "x"})[1]
    for i in range(2):
        a, err = g.check("suggest_more_comparables", {"product_id": "p1", "reason": f"round {i}"})
        assert err is None
        g.record("suggest_more_comparables", a)
    assert "At most 2" in g.check("suggest_more_comparables", {"product_id": "p1", "reason": "again"})[1]
    assert g.check("rank_venues", {"venue_types": ["cafe"]})[1] is None
    assert g.remaining() == ["rank_venues", "match_products", "attach_evidence"]
    g.record("rank_venues", {"venue_types": ["cafe"]})
    assert "before rank_venues" in g.check("suggest_more_comparables", {"product_id": "p2", "reason": "late"})[1]
    assert "must be one of" in g.check("add_venue_type", {"type_id": "cafe", "reason": "already in the run"})[1]
    a, err = g.check("add_venue_type", {"type_id": "bar", "reason": "only 9 cafés"})
    assert err is None
    g.record("add_venue_type", a)
    assert "must be one of ['deli']" in g.check("add_venue_type", {"type_id": "bar", "reason": "again"})[1]
    o = PlanGuard("outreach", {"venue_ids": {"v1"}, "draft_venue_ids": {"v1"}})
    o.record("find_contacts", {})
    assert "subset" in o.check("draft_pitches", {"venue_ids": ["v2"]})[1]


def test_decision_rules():
    """AGT-07: the thresholds the agent is told and the fixed plan applies."""
    assert rules.weak([{"role": "comparable"}]) and rules.weak([])  # nothing found in the wizard counts too
    assert not rules.weak([{"role": "self"}])
    assert not rules.weak([{"role": "comparable"}, {"role": "comparable"}])
    res = {"a": {"weak": True, "suggest_rounds": 1}, "b": {"weak": True, "suggest_rounds": 2}, "c": {"weak": False}}
    assert rules.needs_comparables(res) == ["a"]
    pack = ["cafe", "bar", "restaurant", "deli"]
    assert rules.type_to_add({"cafe": 40, "bar": 9}, ["cafe", "bar"], pack, []) == "restaurant"
    assert rules.type_to_add({"cafe": 40}, ["cafe", "bar"], pack, []) == "restaurant"  # a type with no venues is thin
    assert rules.type_to_add({"cafe": 40, "bar": 20}, ["cafe", "bar"], pack, []) is None
    assert rules.type_to_add({"cafe": 9}, ["cafe"], pack, ["bar", "deli"]) is None  # the cap


def test_ambiguous_us_city_gets_its_state():
    """QLO-12: Qloo reads a bare "Portland" as Oregon; the retry asks for "Portland, Maine"."""
    me = {"name": "Portland", "display_name": "Portland, Cumberland County, Maine, United States", "country": "US"}
    assert qualified_city(me) == "Portland, Maine"
    assert qualified_city({"name": "London", "display_name": "London, Greater London, England, United Kingdom",
                           "country": "gb"}) is None


def test_scraped_email_must_be_the_venues_or_free_mail():
    assert venue_inbox("hi@ipsento.com", "ipsento.com") and venue_inbox("orders@shop.ipsento.com", "ipsento.com")
    assert venue_inbox("ipsento606@gmail.com", "ipsento.com")
    assert not venue_inbox("jack@greensock.com", "ipsento.com")
    # On its owner's domain but named for the venue: kept. A web designer's address: still dropped.
    assert names_venue("cabinjuice@gravityhaus.com", "Cabin Juice", "cabinjuice.com")
    assert not names_venue("hello@studiodesign.com", "Cabin Juice", "cabinjuice.com")
    assert not names_venue("sandwichshop@gmail.com", "Yampa Sandwich Co.", None)  # a generic word ties nothing


def test_free_mail_ranks_below_the_venues_own_domain():
    gmail = Candidate("cafebookings@gmail.com", "osm", "generic", sources=[{"freemail": True}])
    own = Candidate("info@cafe.test", "website", "generic")
    assert choose([gmail, own], "cafe.test") is own


def test_web_results_keep_only_this_venues_address():
    found = [("catering@yampasandwichco.com", "https://dir.test/yampa"), ("joessubs@gmail.com", "https://dir.test/yampa"),
             ("yampasandwichco@gmail.com", "https://dir.test/list"), ("sandwichshop@gmail.com", "https://dir.test/other"),
             ("info@agency.test", "https://dir.test/other")]
    # Its own domain and a Gmail inbox carrying its name; neighbours' and agencies' addresses are dropped.
    got = venue_addresses(found, "Yampa Sandwich Co.", "yampasandwichco.com")
    assert got == [("catering@yampasandwichco.com", "https://dir.test/yampa"), ("yampasandwichco@gmail.com", "https://dir.test/list")]
