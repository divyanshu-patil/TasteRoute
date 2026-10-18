# 09. External services (other than Qloo)

## Summary

| Service | Use | Auth | Limits to respect | Cache |
|---|---|---|---|---|
| Ollama Cloud | Agent, profile, comparables, drafts | Bearer API key | Account limits (check your plan) | No |
| Hunter API v2 | Business emails for venue domains | `X-API-KEY` header | Domain search 15 req/s, 500/min; verifier 10 req/s, 300/min; free plan 50 credits/month | 14 days per domain |
| Nominatim | City geocoding | Identifying User-Agent | Max 1 req/s, cache, no autocomplete, no systematic queries | 30 days |
| Overpass API | Venue website and email tags | Identifying User-Agent | No parallel queries, back off on 429/406, light daily use | 7 days per (city, venue type) |
| Website reader | Brand intake pages | None | Robots.txt, timeouts, SSRF guard | 7 days per URL |
| Apollo (optional, off) | Buyers at chains | API key | Free plan limited; reselling Apollo data needs a contract | 14 days |

## Hunter

- **Domain search:** `GET https://api.hunter.io/v2/domain-search?domain=<domain>&limit=10`. Useful response fields: `data.emails[].value`, `type` (personal or generic), `confidence`, `position`, `sources[]` (`uri`, `last_seen_on`, `still_on_page`), `verification.status` (valid, accept_all, unknown).
- **Email verifier:** `GET https://api.hunter.io/v2/email-verifier?email=<email>`. May return `202` while running: poll once. `data.status`: valid, invalid, accept_all, webmail, disposable, unknown.
- **451 `claimed_email`:** the person asked to be excluded. Do not process or store; add to suppression.
- **Errors:** 400 `wrong_params`, `invalid_domain`; 429 rate limit; handle each.
- **Test key:** Hunter provides a test API key that validates parameters and returns a fixed dummy response; use it for wiring tests.
- **Credits:** domain searches use credits; plan for the demo with cached results.
- **Email Finder by name is not used in the MVP** (we do not look up named people beyond what domain search returns).

## Nominatim

- `GET {NOMINATIM_BASE_URL}/search?q=<city>&format=jsonv2&limit=5&addressdetails=1` with `User-Agent: OSM_USER_AGENT`.
- One request per second maximum across the whole app (shared limiter), results cached 30 days.
- Used only for explicit city searches the user types (debounced, minimum 3 characters, not keystroke autocomplete).
- Show "© OpenStreetMap contributors" attribution where OSM data appears.

## Overpass

- `POST {OVERPASS_BASE_URL}` with a query for one venue type inside the city bounding box, returning elements with `website`, `contact:website`, `email`, `contact:email`, `phone`, `contact:phone` tags:
  ```
  [out:json][timeout:90];
  (
    nwr["amenity"="cafe"]["website"](S,W,N,E);
    nwr["amenity"="cafe"]["contact:website"](S,W,N,E);
    nwr["amenity"="cafe"]["email"](S,W,N,E);
    nwr["amenity"="cafe"]["contact:email"](S,W,N,E);
  );
  out center tags;
  ```
- One query at a time across the app (no parallel queries). Cache 7 days. On 429 or 406 wait and retry once.
- The public instance can be overloaded; if it fails during the demo, the cached result for the demo city must already be stored.

## Website reader

- httpx with the SSRF guard (block private, loopback, link-local, metadata IPs on every redirect), 3 redirects max, 1.5 MB cap, `text/html` only, robots.txt checked for fetched paths, `trafilatura` for main text.

## Apollo (optional, disabled by default)

- Only for chains with a purchasing team, behind `APOLLO_ENABLED=true`.
- Not enabled for public demo runs because the app would republish Apollo data to anonymous visitors.
- If enabled, use organisation and people search for the chain's domain and reveal at most one buyer email per chain, with the source shown.

## Failure policy

External services other than Qloo are **non-fatal**: their failure reduces contacts or details but never blocks ranking. Qloo failures are fatal to the scout phase.
