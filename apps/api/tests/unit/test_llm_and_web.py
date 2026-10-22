"""LLM-04, AGT-02, AGT-03 (unit), SEC-02, INT-01, CON-01."""

import socket

import httpx
import pytest
import respx
from pydantic import BaseModel

from tasteroute_api.errors import LLMBadResponse, LLMUnavailable
from tasteroute_api.external import osm
from tasteroute_api.external.website import (
    Page,
    UrlNotAllowed,
    WebsiteReader,
    check_url,
    emails_in,
    extract_text,
    ip_allowed,
    page_emails,
    site_name,
)
from tasteroute_api.llm import LLMResult
from tasteroute_api.llm.fake import FakeProvider
from tasteroute_api.llm.structured import extract_json, structured


class Out(BaseModel):
    names: list[str]


class Recorder:
    def __init__(self, replies):
        self.provider = FakeProvider(replies)

    async def chat(self, messages, **kw):
        return await self.provider.chat(messages, temperature=0, max_tokens=10, timeout=1, tools=kw.get("tools"))


async def test_structured_repairs_once_then_raises():
    r = Recorder([LLMResult("nope"), LLMResult('{"names": ["Aperol"]}')])
    assert (await structured(r, Out, "sys", "user")).names == ["Aperol"]
    assert len(r.provider.calls) == 2
    r = Recorder([LLMResult("nope"), LLMResult("still nope"), LLMResult('{"names": []}')])
    with pytest.raises(LLMBadResponse):
        await structured(r, Out, "sys", "user")
    assert len(r.provider.calls) == 2  # exactly one repair


def test_extract_json_from_fenced_or_chatty_text():
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('prefix {"a": {"b": 2}} suffix') == {"a": {"b": 2}}


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1", "::1", "fd00::1", "0.0.0.0"])
def test_private_addresses_blocked(ip):
    assert not ip_allowed(ip)


async def test_check_url_blocks_schemes_and_private_dns():
    async def private(host: str) -> list[str]:
        return ["10.1.2.3"]

    with pytest.raises(UrlNotAllowed):
        await check_url("file:///etc/passwd")
    with pytest.raises(UrlNotAllowed):
        await check_url("http://internal.test/", private)
    with pytest.raises(UrlNotAllowed):
        await check_url("http://[::1]:8000/")


async def public(host: str) -> list[str]:
    return ["93.184.216.34"]


@respx.mock
async def test_redirect_to_metadata_is_blocked():
    respx.get("https://shop.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://shop.test/").mock(return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/x"}))
    async with httpx.AsyncClient() as http:
        with pytest.raises(UrlNotAllowed):
            await WebsiteReader(http, public).fetch("https://shop.test/")


@respx.mock
async def test_read_site_page_and_text_caps():
    """INT-01: home plus at most 2 same-domain pages, at most 12,000 characters."""
    home = ('<a href="/about">About us</a><a href="/shop">Shop</a><a href="/menu">Menu</a>'
            '<a href="https://other.test/about">x</a><p>' + "cold brew " * 3000 + "</p>")
    respx.get("https://brand.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://brand.test/").mock(return_value=httpx.Response(200, html=home))
    sub = respx.get(url__regex=r"https://brand\.test/(about|shop|menu)").mock(return_value=httpx.Response(200, html="<p>We roast.</p>"))
    async with httpx.AsyncClient() as http:
        site = await WebsiteReader(http, public).read_site("https://brand.test/")
    assert len(site.pages) == 3 and sub.call_count == 2
    assert len(site.text) <= 12_000


@respx.mock
async def test_find_emails_published_only():
    html = ('<a href="mailto:Hello@Cafe.test?subject=hi">Mail</a> wholesale@cafe.test <img src="logo@2x.png">'
            ' example@mysite.com noreply@cafe.test <p>Email info@cafe.test.Hours: 8-6</p>'
            '<script>/* GSAP by jack@greensock.com */</script>')
    respx.get("https://cafe.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://cafe.test/").mock(return_value=httpx.Response(200, html=html))
    respx.get("https://cafe.test/contact").mock(return_value=httpx.Response(404))  # tried when no contact page is linked
    async with httpx.AsyncClient() as http:
        found = await WebsiteReader(http, public).find_emails("https://cafe.test/")
    assert [e for e, _ in found] == ["hello@cafe.test", "wholesale@cafe.test", "info@cafe.test"]


def test_emails_in_every_published_form():
    key = 0x42  # Cloudflare's email protection: a key byte, then each character XORed with it
    scrambled = f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in "cf@cafe.test")
    html = (f'<a href="/cdn-cgi/l/email-protection#{scrambled}">[email&#160;protected]</a>'
            "<p>Wholesale: trade [at] cafe [dot] test</p><p>hello(at)cafe.test</p>"
            "<p>Write to events at cafe dot test</p><p>split<span>@</span>cafe.test</p>"
            '<a href="mailto:orders%40cafe.test">Order</a>'
            '<script type="application/ld+json">{"@type": "CafeOrCoffeeShop", "email": "mailto:info@cafe.test"}</script>'
            "<p>Order at doordash.com, find us @ cafe.test or at the market.</p>")
    got = {e for e, _ in emails_in(Page("https://cafe.test/", html, 200))}
    assert got == {"cf@cafe.test", "trade@cafe.test", "hello@cafe.test", "events@cafe.test", "split@cafe.test",
                   "orders@cafe.test", "info@cafe.test"}  # and no "order@doordash.com" or "us@cafe.test"


@respx.mock
async def test_contact_pages_follow_links_and_repair_urls():
    respx.get("https://deli.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://deli.test/", params={"ss_source": "ads"}).mock(return_value=httpx.Response(200, html="<p>Hi</p>"))
    home = '<a href="/menu">Menu</a><a href="/about-us">About</a><a href="/contact-us">Contact</a> reservations@deli.test'
    respx.get("https://deli.test/").mock(return_value=httpx.Response(200, html=home))
    respx.get("https://deli.test/contact-us").mock(return_value=httpx.Response(200, html="<p>Trade: trade [at] deli [dot] test</p>"))
    respx.get("https://deli.test/about-us").mock(return_value=httpx.Response(200, html="<p>Since 1990</p>"))
    respx.get("https://deli.test/contact").mock(return_value=httpx.Response(404))
    respx.get("https://deli.test/old-page").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as http:
        r = WebsiteReader(http, public)
        pages = await r.contact_pages("https://deli.test/old-page")  # a dead deep link falls back to the homepage
        # the contact page is read even though the homepage already shows an address; the menu is not
        assert [p.url for p in pages] == ["https://deli.test/", "https://deli.test/contact-us", "https://deli.test/about-us"]
        assert page_emails(pages) == [("reservations@deli.test", "https://deli.test/"),
                                      ("trade@deli.test", "https://deli.test/contact-us")]
        mangled = await r.contact_pages("https://deli.test/%3Fss_source%3Dads")  # "?" percent-encoded into the path
        assert mangled[0].url == "https://deli.test/?ss_source=ads"


def test_addresses_are_read_never_assembled():
    """CON-08: words that only hint at an address give nothing; a spelled-out address is read exactly."""
    hint = Page("https://oslocoffee.com/contact", "<p>For wholesale, contact our sales team by email at oslocoffee.com</p>"
                "<p>orders, then the at sign, then oslocoffee.com</p>", 200)
    assert emails_in(hint) == []
    spelled = Page("https://oslocoffee.com/contact", "<p>Wholesale: hello [at] oslocoffee [dot] com</p>", 200)
    assert emails_in(spelled) == [("hello@oslocoffee.com", "https://oslocoffee.com/contact")]


def test_free_mail_counts_only_when_the_page_labels_it():
    """CON-08: an owner's personal Gmail on the venue's site isn't its inbox unless the page says it is."""
    from tasteroute_api.services.contacts import labelled_contact

    footer = Page("https://cafe.test/", "<footer>Site by ana.lopez@gmail.com</footer>", 200)
    booking = Page("https://cafe.test/", "<p>Bookings and events: cafebookings@gmail.com</p>", 200)
    link = Page("https://cafe.test/", '<a href="mailto:owner.cafe@gmail.com">Email us</a>', 200)
    assert not labelled_contact("ana.lopez@gmail.com", footer)
    assert labelled_contact("cafebookings@gmail.com", booking) and labelled_contact("owner.cafe@gmail.com", link)


def test_extract_text_strips_scripts():
    assert "alert" not in extract_text("<script>alert(1)</script><p>Hello there friend, this is our cafe.</p>")


def test_osm_match_by_name_and_distance():
    els = [{"id": "node/1", "lat": 40.7, "lon": -73.95, "tags": {"name": "Oslo Coffee Roasters", "email": "hi@oslo.test"}},
           {"id": "node/2", "lat": 40.7, "lon": -73.95, "tags": {"name": "Other Place"}}]
    assert osm.match_osm("Oslo Coffee Roasters", 40.7005, -73.9505, els)["id"] == "node/1"
    assert osm.match_osm("Oslo Coffee Roasters", 40.75, -73.95, els) is None  # > 150 m away
    assert osm.match_osm("Totally Different", 40.7, -73.95, els) is None


async def test_fake_provider_plays_plan_then_finishes():
    p = FakeProvider()
    tools = [{"function": {"name": n}} for n in ("find_contacts", "draft_pitches", "finish_phase")]
    r1 = await p.chat([], tools=tools, temperature=0, max_tokens=1, timeout=1)
    assert r1.tool_calls[0].name == "find_contacts"
    done = [{"role": "tool", "tool_name": "find_contacts"}, {"role": "tool", "tool_name": "draft_pitches"}]
    r2 = await p.chat(done, tools=tools, temperature=0, max_tokens=1, timeout=1)
    assert r2.tool_calls[0].name == "finish_phase"


def test_tests_cannot_reach_the_internet():
    with pytest.raises(AssertionError, match="network access in tests"):
        socket.create_connection(("1.1.1.1", 80), timeout=1)


def test_site_name_from_title_and_og():
    html = '<meta property="og:site_name" content="Oslo Coffee"><title>Shop &amp; Cafés | Oslo Coffee</title>'
    assert site_name(html) == "Site name: Oslo Coffee | Shop & Cafés | Oslo Coffee"
    assert site_name("<p>no head</p>") == ""


@respx.mock
async def test_ollama_stream_yields_chunks_then_usage():
    from tasteroute_api.llm.ollama_cloud import OllamaCloudProvider

    body = (b'{"message":{"content":"#1 "},"done":false}\n\n{"message":{"content":"Bar"},"done":false}\n'
            b'{"message":{"content":""},"done":true,"prompt_eval_count":12,"eval_count":3}\n')
    respx.post("https://llm.test/api/chat").mock(return_value=httpx.Response(200, content=body))
    p = OllamaCloudProvider(base_url="https://llm.test", api_key="k", model="m")
    got = [c async for c in p.stream([{"role": "user", "content": "q"}], temperature=0, max_tokens=10, timeout=5)]
    assert got == ["#1 ", "Bar", {"input_tokens": 12, "output_tokens": 3}]
    respx.post("https://llm.test/api/chat").mock(return_value=httpx.Response(500))
    with pytest.raises(LLMUnavailable):
        [c async for c in p.stream([], temperature=0, max_tokens=10, timeout=5)]
