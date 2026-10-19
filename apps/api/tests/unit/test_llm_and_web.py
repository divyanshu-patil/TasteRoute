"""LLM-04, AGT-02, AGT-03 (unit), SEC-02, INT-01, CON-01."""

import httpx
import pytest
import respx
from pydantic import BaseModel

from stockist_api.errors import LLMBadResponse
from stockist_api.external import osm
from stockist_api.external.website import UrlNotAllowed, WebsiteReader, check_url, extract_text, ip_allowed
from stockist_api.llm import LLMResult
from stockist_api.llm.fake import FakeProvider
from stockist_api.llm.structured import extract_json, structured


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
    html = '<a href="mailto:Hello@Cafe.test?subject=hi">Mail</a> wholesale@cafe.test <img src="logo@2x.png">'
    respx.get("https://cafe.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://cafe.test/").mock(return_value=httpx.Response(200, html=html))
    async with httpx.AsyncClient() as http:
        found = await WebsiteReader(http, public).find_emails("https://cafe.test/")
    assert [e for e, _ in found] == ["hello@cafe.test", "wholesale@cafe.test"]


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
