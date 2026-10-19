"""Hunter domain search and email verifier (F06). Used only when HUNTER_API_KEY is set (D-08)."""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import asyncpg
import httpx
import tldextract

from . import Emit, cached_call

BASE = "https://api.hunter.io/v2"
SKIP_DOMAINS = {
    "instagram.com", "facebook.com", "linktr.ee", "zomato.com", "swiggy.com", "ubereats.com", "doordash.com",
    "grubhub.com", "yelp.com", "tripadvisor.com", "google.com", "toasttab.com", "square.site", "resy.com",
    "opentable.com", "seamless.com", "tiktok.com", "twitter.com", "x.com", "linkedin.com", "wixsite.com",
    "squarespace.com", "shopify.com", "business.site", "sites.google.com",
}
ROLE_WORDS = ("owner", "founder", "manager", "buyer", "purchas", "beverage", "bar", "coffee", "general", "director")
_extract = tldextract.TLDExtract(suffix_list_urls=())  # bundled list, no network


class HunterClaimed(Exception):
    """451: the person asked to be excluded."""


@dataclass
class HunterEmail:
    value: str
    type: str | None
    confidence: int | None
    position: str | None
    verification: str | None
    sources: list[dict[str, Any]] = field(default_factory=list)


def registrable_domain(url: str) -> str | None:
    ext = _extract(url)
    if not ext.domain or not ext.suffix:
        return None
    return f"{ext.domain}.{ext.suffix}".lower()


def skip_domain(domain: str | None) -> bool:
    return not domain or domain in SKIP_DOMAINS or any(domain.endswith("." + d) for d in SKIP_DOMAINS)


def is_role(position: str | None) -> bool:
    return bool(position) and any(w in position.lower() for w in ROLE_WORDS)  # type: ignore[union-attr]


async def domain_search(
    pool: asyncpg.Pool, http: httpx.AsyncClient, api_key: str, domain: str, *, run_id: str | None, emit: Emit | None
) -> tuple[list[HunterEmail], str]:
    async def fetch() -> tuple[int, Any]:
        for attempt in range(2):
            r = await http.get(f"{BASE}/domain-search", params={"domain": domain, "limit": 10},
                               headers={"X-API-KEY": api_key}, timeout=20)
            if r.status_code == 429 and attempt == 0:
                await asyncio.sleep(2)
                continue
            return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else None
        return 429, None

    status, body, call_id, _ = await cached_call(
        pool, "hunter", "/domain-search", {"domain": domain}, timedelta(days=14), fetch, run_id=run_id, emit=emit
    )
    if status == 451:
        raise HunterClaimed(domain)
    if status != 200 or not body:
        return [], call_id
    out = []
    for e in (body.get("data") or {}).get("emails", []):
        if not e.get("value"):
            continue
        out.append(HunterEmail(
            value=e["value"].lower(),
            type=e.get("type"),
            confidence=e.get("confidence"),
            position=e.get("position"),
            verification=(e.get("verification") or {}).get("status"),
            sources=[{"uri": s.get("uri"), "last_seen_on": s.get("last_seen_on")} for s in (e.get("sources") or [])[:3]],
        ))
    return out, call_id


async def verify(
    pool: asyncpg.Pool, http: httpx.AsyncClient, api_key: str, email: str, *, run_id: str | None, emit: Emit | None,
    sleep: Any = asyncio.sleep,
) -> str | None:
    async def fetch() -> tuple[int, Any]:
        for attempt in range(2):
            r = await http.get(f"{BASE}/email-verifier", params={"email": email}, headers={"X-API-KEY": api_key}, timeout=20)
            if r.status_code == 202 and attempt == 0:
                await sleep(3)
                continue
            return r.status_code, r.json() if r.status_code == 200 else None
        return 202, None

    status, body, _, _ = await cached_call(
        pool, "hunter", "/email-verifier", {"email": email}, timedelta(days=14), fetch, run_id=run_id, emit=emit
    )
    if status == 451:
        raise HunterClaimed(email)
    return ((body or {}).get("data") or {}).get("status") if status == 200 else None
