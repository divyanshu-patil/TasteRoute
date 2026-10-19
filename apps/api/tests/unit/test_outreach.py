"""DRF-02..05, EXP-01, EXP-02, CON-02, CON-03, CON-07, AGT-01."""

import csv
import io
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from tasteroute_api.agent.plan_guard import PlanGuard
from tasteroute_api.errors import AppError
from tasteroute_api.external import hunter
from tasteroute_api.grounding import Bundle, validate
from tasteroute_api.services.contacts import Candidate, choose, is_suppressed, venue_inbox
from tasteroute_api.services.drafts import next_status, short_name, template_draft
from tasteroute_api.services.export import CSV_COLUMNS, MAILTO_BODY_MAX, mailto, mask, to_csv

OPT_OUT = "If you'd rather not hear from me, reply 'no thanks' and I won't contact you again."


def bundle(**kw) -> Bundle:
    base = dict(
        venue_name="Oslo Coffee Roasters", venue_type="Cafés", brand_name="Fieldnote Coffee", sender_name="Mara",
        product_names=["Cold Brew Concentrate", "House Espresso"], best_product="Cold Brew Concentrate",
        reason="Guests here over-index on espresso bar (Qloo).",
        evidence={"e1": "Guests over-index on Espresso bar, Specialty coffee", "e2": "Fans of Blue Bottle Coffee like this venue"},
        contact_role=None, ask_examples=["send a free sample", "drop by for a 10-minute tasting"], opt_out_line=OPT_OUT,
    )
    return Bundle(**{**base, **kw})


GOOD = (f"Hi Oslo Coffee Roasters team,\n\nI'm Mara from Fieldnote Coffee. Your guests over-index on espresso bar and "
        f"specialty coffee. I think Cold Brew Concentrate would suit you. Could I drop by for a 10-minute tasting?\n\nMara\n\n{OPT_OUT}")


def test_validator_accepts_grounded_draft():
    assert validate("Cold Brew Concentrate for Oslo Coffee Roasters", GOOD, ["e1"], bundle()) == []


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


def test_template_always_passes_validator():
    for ev in ({}, {"e1": "Crowd: Locals. Interests: Specialty coffee"}, bundle().evidence):
        b = bundle(evidence=ev or {"x": "Qloo taste fit and popularity baseline"})
        t = template_draft(b)
        assert OPT_OUT in t.body  # DRF-05
        assert validate(t.subject, t.body, t.cited_evidence_ids, b) == [], t.body


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
    g = PlanGuard("scout", {"product_ids": {"p1", "p2"}, "venue_types": {"cafe"}})
    assert "Unknown tool" in g.check("send_email", {})[1]
    assert "before" in g.check("rank_venues", {})[1]
    assert "exactly" in g.check("resolve_entities", {"product_ids": ["p1", "zzz"]})[1]
    assert "Invalid arguments" in g.check("resolve_entities", {"oops": 1})[1]
    args, err = g.check("resolve_entities", {"product_ids": ["p2", "p1"]})
    assert err is None
    g.record("resolve_entities", args)
    assert "already called" in g.check("resolve_entities", {"product_ids": ["p2", "p1"]})[1]
    assert g.check("rank_venues", {"venue_types": ["cafe"]})[1] is None
    assert g.remaining() == ["rank_venues", "match_products", "attach_evidence"]
    o = PlanGuard("outreach", {"venue_ids": {"v1"}, "draft_venue_ids": {"v1"}})
    o.record("find_contacts", {})
    assert "subset" in o.check("draft_pitches", {"venue_ids": ["v2"]})[1]


def test_scraped_email_must_be_the_venues_or_free_mail():
    assert venue_inbox("hi@ipsento.com", "ipsento.com") and venue_inbox("orders@shop.ipsento.com", "ipsento.com")
    assert venue_inbox("ipsento606@gmail.com", "ipsento.com")
    assert not venue_inbox("jack@greensock.com", "ipsento.com")
