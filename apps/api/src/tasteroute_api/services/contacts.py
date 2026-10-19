"""F06: public business contacts for selected venues. Emails are copied from a source, never constructed (CON-05)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import asyncpg

from ..agent.context import RunContext
from ..errors import AppError
from ..external import cached_call, hunter, osm
from ..external.website import WebsiteReader, clean_email

BAD_VERIFICATION = {"invalid", "disposable"}
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

    for v in rows:
        vid = v["id"]
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
            async def read(url: str = website) -> tuple[int, Any]:
                try:
                    return 200, [list(x) for x in await reader.find_emails(url)]
                except AppError as e:
                    return 422, {"error": e.detail}

            code, found_emails, _, _ = await cached_call(ctx.pool, "website", "/emails", {"url": website}, timedelta(days=7),
                                                         read, run_id=ctx.run_id, emit=ctx.emit)
            for raw, page in found_emails if code == 200 else []:
                if email := clean_email(raw):  # also tidies results cached before clean_email existed
                    cands.append(Candidate(email, "website", "generic", purpose(email)[1], sources=[{"uri": page}]))
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
    with_contact = await ctx.pool.fetch(
        "select distinct venue_id from contacts where run_id = $1 and is_primary and venue_id = any($2::uuid[])",
        ctx.rid, [r["id"] for r in rows],
    )
    return {"checked": len(rows), **{k: v for k, v in counts.items() if v},
            "venue_ids_with_contact": [str(r["venue_id"]) for r in with_contact]}
