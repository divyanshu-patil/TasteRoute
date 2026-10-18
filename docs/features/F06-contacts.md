# F06. Business contact discovery

## Purpose

For venues the user selects, find a **public business contact** (an email address published for the business, ideally the owner, manager or buyer) with its source, without guessing.

## Rules

- Business contacts only, for the venue's own domain or as listed publicly for the venue. No consumer data. No guessed patterns such as `firstname@domain`.
- Contact lookups run **only when the user clicks** "Find contacts" for selected venues (maximum `MAX_OUTREACH_VENUES_PER_RUN`).
- Hunter calls per run are capped by `HUNTER_MAX_CALLS_PER_RUN`.
- Suppressed emails and domains (F08) are skipped before any lookup.

## How it works (per venue)

1. **Find the venue website.**
   a. From Qloo entity properties, if the verified contract includes a website.
   b. Otherwise from OpenStreetMap: one Overpass query per (city, venue type) fetches venues with `website`, `contact:website`, `email`, `contact:email` tags inside the city bounding box. Results are cached for 7 days. Match a Qloo venue to an OSM element by name similarity ≥ 0.85 **and** distance ≤ 150 m.
2. **Email listed on OpenStreetMap.** If the matched OSM element has `email` or `contact:email`, record it with source `osm`.
3. **Hunter domain search** on the website's registrable domain (skip social-media and marketplace domains such as instagram.com, facebook.com, linktr.ee, zomato.com, swiggy.com, ubereats.com):
   `GET https://api.hunter.io/v2/domain-search?domain=<domain>&limit=10` with the key in the `X-API-KEY` header.
   - Keep emails whose `position` suggests owner, founder, manager, buyer, purchasing, or beverage/bar/coffee lead; otherwise keep `generic` emails such as `hello@`, `info@`, `orders@`.
   - Record `value`, `type`, `confidence`, `position`, `verification.status`, and up to 3 `sources` (`uri`, `last_seen_on`).
4. **Optional verification.** If the best email's `verification.status` is not `valid`, call the Email Verifier (`/v2/email-verifier?email=`). Handle `202` by polling once after 3 seconds. Use the returned `status` (`valid`, `invalid`, `accept_all`, `webmail`, `disposable`, `unknown`).
5. **Choose the contact**: verified role email, then verified generic email, then OSM email, then unverified Hunter email (labelled "unverified"). `invalid` and `disposable` are never used.
6. **HTTP 451 `claimed_email`** from Hunter means the person asked to be excluded: add it to the suppression list automatically and do not store the address.
7. No result: store "no public business email found" with the list of sources checked.

## Outputs and storage

`contacts` rows: venue_id, workspace_id, email, role, type, source (`hunter`, `osm`, `qloo`), confidence, verification_status, sources JSON, found_at. `external_calls` rows for Overpass and Hunter.

## Failure handling

| Failure | Behaviour |
|---|---|
| Overpass 429 or timeout | Back off (30 s, then 60 s), one retry, then continue without OSM data |
| Hunter 429 | Respect limits (15 req/s, 500/min for domain search); back off and retry once |
| Hunter credits exhausted or cap reached | Stop lookups, mark remaining venues "not checked (limit reached)" |
| Website is a social profile | Skip Hunter for that venue |

## UI

Outreach page: selected venues with contact status (found, unverified, none, not checked), source chips, and a "why this email" popover showing Hunter sources.

## Tests

| What | How |
|---|---|
| OSM matching by name and distance | Unit tests |
| Domain extraction and social-domain skip list | Unit tests |
| Role filtering and choice order | Unit tests with Hunter fixtures |
| 451 adds to suppression and stores nothing | Integration test with respx |
| 202 polling for verifier | Integration test |
| Hunter cap stops lookups | Integration test |
| No email is ever constructed from a name pattern | Unit test on the contact builder (only accepts addresses from sources) |

Acceptance: CON-01 to CON-07, SEC-02.
