"""F06: public business contacts for selected venues. Emails are copied from a source, never constructed (CON-05)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import asyncpg
from pydantic import BaseModel

from ..agent.context import RunContext
from ..errors import AppError, LLMBadResponse, LLMUnavailable
from ..external import cached_call, hunter, osm
from ..external.website import EMAIL, Page, WebsiteReader, clean_email, deobfuscate, page_emails, visible_text
from ..llm import web_search
from ..llm.prompts import load
from ..llm.structured import structured

BAD_VERIFICATION = {"invalid", "disposable"}
# A scraped address must be on the venue's own domain or a free-mail inbox; anything else is usually the web agency's or a widget's.
FREEMAIL = {"gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com", "icloud.com", "me.com",
            "aol.com", "proton.me", "protonmail.com", "gmx.com", "fastmail.com"}
# Which inbox a supplier's first pitch should reach, best first. Anything unlisted ranks between "main" and "other".
PURPOSES = [
    (re.compile(r"^(wholesale|trade|sales|orders?|buy(ing|er)|purchas\w*|procure\w*|stockists?|partners?(hips?)?)\b"), "sales inbox"),
    (re.compile(r"^(info|hello|hi|hey|contact|general|office|team|mail|owners?|manager|host|inquir\w*|enquir\w*)\b"), "main inbox"),
    (re.compile(r"^(reserv\w*|book\w*|events?|private\w*|catering|jobs?|careers?|hiring|press|media|pr|marketing|privacy"
                r"|legal|support|billing|abuse|webmaster|admin|gift\w*)\b"), None),
]


@dataclass
class Candidate:
    email: str
    source: str  # hunter | osm | website | qloo
    type: str | None = None
    role: str | None = None
    confidence: int | None = None
    verification: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)

    @property
    def domain(self) -> str:
        return self.email.rsplit("@", 1)[-1].lower()


def venue_inbox(email: str, domain: str | None) -> bool:
    d = email.rsplit("@", 1)[-1]
    return not domain or d in FREEMAIL or d == domain or d.endswith("." + domain)


# Words in many venue names, so they don't tie an address to this venue
GENERIC = {"coffee", "bakery", "bagels", "kitchen", "restaurant", "sandwich", "sandwiches", "brewing", "brewery", "tavern",
           "bistro", "lounge", "market", "grille", "pizzeria", "eatery", "cantina", "taproom", "roasters", "roastery",
           "cocktails", "company", "saloon", "canteen", "brasserie", "trattoria", "osteria", "creamery", "juicery"}


def squash(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())


def venue_keys(name: str, domain: str | None) -> set[str]:
    """Distinctive strings for a venue: its whole name, its longer non-generic words, its domain's name."""
    keys = {squash(name), (domain or "").split(".")[0], *(squash(w) for w in name.split() if squash(w) not in GENERIC)}
    return {k for k in keys if len(k) >= 6}


def names_venue(email: str, name: str, domain: str | None) -> bool:
    """An address on another domain that carries the venue's name, e.g. cabinjuice@gravityhaus.com (its owner's)."""
    local, _, d = email.partition("@")
    return any(k in squash(local + d.split(".")[0]) for k in venue_keys(name, domain))


def emails_from_results(results: list[dict[str, str]], name: str, domain: str | None) -> list[tuple[str, str]]:
    """Addresses in web search results that belong to this venue: on its own domain, or carrying its name. A directory
    page lists many businesses, so any other address on it is dropped. (email, result url)"""
    out: dict[str, str] = {}
    for r in results:
        for raw in EMAIL.findall(deobfuscate(r["content"])):
            e = clean_email(raw)
            d = (e or "").rsplit("@", 1)[-1]
            if e and (bool(domain) and (d == domain or d.endswith(f".{domain}")) or names_venue(e, name, domain)):
                out.setdefault(e, r["url"])
    return list(out.items())


class EmailOnPage(BaseModel):
    email: str | None = None
    quote: str | None = None
    page: str | None = None


def quoted(email: str, quote: str, text: str) -> bool:
    """The model's quote is really on the page and spells this address out: local part, then each domain label."""
    q, t = " ".join(quote.lower().split()), " ".join(text.lower().split())
    if not q or q not in t:
        return False
    at = 0
    local, _, domain = email.lower().partition("@")
    for part in [local, *domain.split(".")]:
        at = q.find(part, at)
        if at < 0:
            return False
        at += len(part)
    return True


async def ai_email(llm: Any, run_id: str | None, venue: str, pages: list[Page]) -> tuple[str, str] | None:
    """AI fallback when no pattern matched: the model reads the pages and must quote the address from one of them.
    The quote is checked against the page text, so an address can be found this way but never made up (CON-05).
    Raises LLMUnavailable or LLMBadResponse when the model can't answer."""
    texts = {p.url: visible_text(p.html) for p in pages}
    user = f"Venue: {venue}\n\n" + "\n\n".join(  # the start and the footer, where addresses usually are
        f"<page url=\"{u}\">\n{t if len(t) <= 4000 else t[:2000] + ' … ' + t[-2000:]}\n</page>" for u, t in texts.items())
    prompt, version = load("find_email")
    out = await structured(llm, EmailOnPage, prompt, user, purpose="find_email", prompt_version=version, run_id=run_id,
                           temperature=0, max_tokens=300)
    email = clean_email(out.email or "")
    page = out.page if out.page in texts else next((u for u, t in texts.items() if quoted(email or "", out.quote or "", t)), None)
    if not email or not page or not quoted(email, out.quote or "", texts[page]):
        return None
    return email, page


def purpose(email: str) -> tuple[int, str | None]:
    """(rank, label) for the local part: sales/wholesale 0, main inbox 1, unknown 2, reservations/careers/press 3."""
    local = email.split("@", 1)[0].lower()
    for i, (pat, label) in enumerate(PURPOSES):
        if pat.match(local):
            return (i if i < 2 else 3), label
    return 2, None


def choose(cands: list[Candidate], domain: str | None = None) -> Candidate | None:
    """Verified role (Hunter) → verified generic (Hunter) → published (OSM, venue website) → unverified Hunter (CON-03).
    Among published addresses: the venue's own domain, then the inbox that suits a supplier pitch, then OSM over website."""
    usable = [c for c in cands if (c.verification or "").lower() not in BAD_VERIFICATION]

    def order(c: Candidate) -> tuple[int, int, int, int, int]:
        if c.source == "hunter" and c.verification == "valid":
            tier = 0 if hunter.is_role(c.role) else 1
        else:
            tier = 3 if c.source == "hunter" else 2
        # A scraped address on another domain may be the web agency's; OSM's email tag is the venue's own listing.
        off = int(c.source == "website" and bool(domain) and c.domain != domain and not c.domain.endswith("." + str(domain)))
        src = {"osm": 0, "website": 1, "qloo": 1}.get(c.source, 2)
        return tier, off, purpose(c.email)[0], src, -(c.confidence or 0)

    usable.sort(key=order)
    return usable[0] if usable else None


async def suppression_sets(pool: asyncpg.Pool, workspace_id: str) -> tuple[set[str], set[str]]:
    rows = await pool.fetch("select kind, value from suppressions where workspace_id = $1", uuid.UUID(workspace_id))
    emails = {str(r["value"]).lower() for r in rows if r["kind"] == "email"}
    domains = {str(r["value"]).lower() for r in rows if r["kind"] == "domain"}
    return emails, domains


def is_suppressed(email: str, emails: set[str], domains: set[str]) -> bool:
    e = email.lower()
    d = e.rsplit("@", 1)[-1]
    return e in emails or d in domains or any(d.endswith("." + x) for x in domains)


async def suppress(pool: asyncpg.Pool, workspace_id: str, kind: str, value: str, reason: str) -> None:
    await pool.execute(
        "insert into suppressions (workspace_id, kind, value, reason) values ($1,$2,$3,$4) on conflict do nothing",
        uuid.UUID(workspace_id), kind, value.lower(), reason,
    )


class TooManyVenues(AppError):
    code, status, title = "validation_error", 422, "Too many venues selected"


async def find_contacts(ctx: RunContext, venue_ids: list[str]) -> dict[str, Any]:
    s = ctx.svc.settings
    if len(venue_ids) > s.max_outreach_venues_per_run:
        raise TooManyVenues(f"Select at most {s.max_outreach_venues_per_run} venues.")
    rows = await ctx.pool.fetch(
        "select v.*, vs.venue_type from venue_scores vs join venues v on v.id = vs.venue_id "
        "where vs.run_id = $1 and vs.venue_id = any($2::uuid[]) order by vs.rank",
        ctx.rid, [uuid.UUID(v) for v in venue_ids],
    )
    sup_emails, sup_domains = await suppression_sets(ctx.pool, ctx.workspace_id)
    hunter_key = s.hunter_api_key.get_secret_value()
    hunter_used = int(await ctx.pool.fetchval(
        "select count(*) from external_calls where run_id = $1 and service = 'hunter' and cache_hit = false", ctx.rid))
    reader = WebsiteReader(ctx.svc.http, timeout=s.website_fetch_timeout_seconds)
    osm_cache: dict[str, list[dict[str, Any]]] = {}
    counts = {"found": 0, "none": 0, "limit_reached": 0, "suppressed": 0, "skipped_social": 0, "error": 0}

    for i, v in enumerate(rows):
        vid = v["id"]
        # Live progress for the outreach page (one venue at a time)
        await ctx.emit("venue", {"tool": "find_contacts", "venue": v["name"], "state": "checking", "done": i, "of": len(rows)})
        checked: list[str] = []
        cands: list[Candidate] = []
        status = "none"
        website = v["website"]
        # OpenStreetMap: email and website tags (CON-01)
        vt = ctx.pack.venue_type(v["venue_type"])
        if vt and ctx.city.get("bbox"):
            key = vt.id
            if key not in osm_cache:
                osm_cache[key], _ = await osm.venue_tags(
                    ctx.pool, ctx.svc.http, s.overpass_base_url, s.osm_user_agent, key=vt.osm.key, value=vt.osm.value,
                    bbox=ctx.city["bbox"], run_id=ctx.run_id, emit=ctx.emit,
                )
            checked.append("openstreetmap")
            m = osm.match_osm(v["name"], v["lat"], v["lon"], osm_cache[key])
            if m:
                tags = m["tags"]
                if not website:
                    website = tags.get("website") or tags.get("contact:website")
                email = tags.get("email") or tags.get("contact:email")
                email = clean_email(email.split(";")[0]) if email else None  # OSM allows "a@x.com;b@x.com"
                if email:
                    cands.append(Candidate(email, "osm", "generic", purpose(email)[1],
                                           sources=[{"uri": f"https://www.openstreetmap.org/{m['id']}"}]))
                await ctx.pool.execute(
                    "update venues set osm_ref = $2, website = coalesce(website, $3) where id = $1", vid, m["id"], website)
                await ctx.pool.execute(
                    "insert into venue_evidence (run_id, venue_id, type, label, value, source_kind) "
                    "values ($1,$2,'osm_fact','OpenStreetMap listing',$3,'external')",
                    ctx.rid, vid, {"osm_id": m["id"], **{k: tags[k] for k in tags if k != "name"}},
                )
        domain = hunter.registrable_domain(website) if website else None
        if domain and domain in sup_domains:
            status = "suppressed"
        elif website and hunter.skip_domain(domain):
            checked.append("website (social or marketplace, skipped)")
            status = "skipped_social" if not cands else "found"
        elif website:
            # The venue's own site (D-08)
            checked.append("venue website")
            async def read(url: str = website, name: str = v["name"]) -> tuple[int, Any]:
                try:
                    pages = await reader.contact_pages(url)
                except AppError as e:
                    return 422, {"error": e.detail}
                found = [[e, u, "page"] for e, u in page_emails(pages)]
                if found:
                    return 200, {"emails": found, "ai_read": False}
                try:
                    ai = await ai_email(ctx.svc.llm, ctx.run_id, name, pages)
                except (LLMUnavailable, LLMBadResponse):
                    return 503, {"error": "The AI could not read the site"}  # not cached: tried again next run
                return 200, {"emails": [[*ai, "ai"]] if ai else [], "ai_read": True}

            code, body, _, _ = await cached_call(ctx.pool, "website", "/emails", {"url": website, "v": 2}, timedelta(days=7),
                                                 read, run_id=ctx.run_id, emit=ctx.emit)
            if code == 200 and body["ai_read"]:
                checked.append("venue website (read by AI)")
            for raw, page, how in body["emails"] if code == 200 else []:
                email = clean_email(raw)
                if email and (venue_inbox(email, domain) or names_venue(email, v["name"], domain)):
                    src = {"uri": page, **({"found_by": "ai"} if how == "ai" else {})}
                    cands.append(Candidate(email, "website", "generic", purpose(email)[1], sources=[src]))
            # Hunter domain search, capped per run (CON-02, CON-06)
            if hunter_key and domain:
                if hunter_used >= s.hunter_max_calls_per_run:
                    checked.append("hunter (limit reached)")
                    if not cands:
                        status = "limit_reached"
                else:
                    checked.append("hunter")
                    hunter_used += 1
                    try:
                        found, _ = await hunter.domain_search(ctx.pool, ctx.svc.http, hunter_key, domain,
                                                              run_id=ctx.run_id, emit=ctx.emit)
                        keep = [h for h in found if hunter.is_role(h.position) or h.type == "generic"]
                        for h in keep:
                            cands.append(Candidate(h.value, "hunter", h.type, h.position, h.confidence, h.verification, h.sources))
                    except hunter.HunterClaimed:
                        await suppress(ctx.pool, ctx.workspace_id, "domain", domain, "claimed_email")
                        sup_domains.add(domain)
                        status = "suppressed"
        # Last resort: a web search, when nothing above found an address (uses the LLM key; cached 14 days)
        if status != "suppressed" and not cands and web_search.enabled(s):
            checked.append("web search")
            results = await web_search.search(ctx.pool, ctx.svc.http, s, f'"{v["name"]}" {ctx.city.get("name", "")} email',
                                              run_id=ctx.run_id, emit=ctx.emit)
            for email, url in emails_from_results(results, v["name"], domain):
                cands.append(Candidate(email, "web", "generic", purpose(email)[1], sources=[{"uri": url, "found_by": "web_search"}]))
        if status != "suppressed":
            cands = [c for c in cands if not is_suppressed(c.email, sup_emails, sup_domains)]
            best = choose(cands, domain)
            if best and best.source == "hunter" and best.verification != "valid" and hunter_key \
                    and hunter_used < s.hunter_max_calls_per_run:
                hunter_used += 1
                try:
                    best.verification = await hunter.verify(ctx.pool, ctx.svc.http, hunter_key, best.email,
                                                            run_id=ctx.run_id, emit=ctx.emit)
                except hunter.HunterClaimed:
                    await suppress(ctx.pool, ctx.workspace_id, "email", best.email, "claimed_email")
                    cands = [c for c in cands if c.email != best.email]
                best = choose(cands, domain)
            await ctx.pool.execute("delete from contacts where run_id = $1 and venue_id = $2", ctx.rid, vid)
            if best:
                status = "found"
                rest = sorted((c for c in cands if c.email != best.email), key=lambda c: purpose(c.email)[0])
                for c in [best] + list({c.email: c for c in rest}.values())[:2]:
                    await ctx.pool.execute(
                        "insert into contacts (workspace_id, run_id, venue_id, email, role, type, source, confidence, "
                        "verification_status, sources, is_primary) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) "
                        "on conflict (run_id, venue_id, email) do nothing",
                        uuid.UUID(ctx.workspace_id), ctx.rid, vid, c.email, c.role, c.type, c.source, c.confidence,
                        c.verification, c.sources, c is best,
                    )
                await ctx.pool.execute(
                    "insert into venue_evidence (run_id, venue_id, type, label, value, source_kind) "
                    "values ($1,$2,'contact_source','Where this email was published',$3,'external')",
                    ctx.rid, vid, {"email": best.email, "source": best.source, "sources": best.sources,
                                   "verification": best.verification},
                )
        counts[status] = counts.get(status, 0) + 1
        await ctx.pool.execute(
            "insert into contact_checks (run_id, venue_id, status, checked_sources) values ($1,$2,$3,$4) "
            "on conflict (run_id, venue_id) do update set status = excluded.status, checked_sources = excluded.checked_sources, "
            "checked_at = now()",
            ctx.rid, vid, status, checked,
        )
        await ctx.emit("venue", {"tool": "find_contacts", "venue": v["name"], "state": "done", "result": status,
                                 "done": i + 1, "of": len(rows)})
    with_contact = await ctx.pool.fetch(
        "select distinct venue_id from contacts where run_id = $1 and is_primary and venue_id = any($2::uuid[])",
        ctx.rid, [r["id"] for r in rows],
    )
    return {"checked": len(rows), **{k: v for k, v in counts.items() if v},
            "venue_ids_with_contact": [str(r["venue_id"]) for r in with_contact]}
