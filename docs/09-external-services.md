# 09. External services (other than Qloo)

## Summary

| Service | Use | Auth | Limits to respect | Cache |
|---|---|---|---|---|
| Ollama Cloud | Agent, profile, comparables, drafts | Bearer API key | Account limits (check your plan) | No |
| Hunter API v2 | Business emails for venue domains | `X-API-KEY` header | Domain search 15 req/s, 500/min; verifier 10 req/s, 300/min; free plan 50 credits/month | 14 days per domain |
| Nominatim | City and business-location geocoding, reverse lookup of a dropped pin | Identifying User-Agent | Max 1 req/s, cache, no autocomplete, no systematic queries | 30 days |
| Photon (komoot) | Place suggestions while the user types | Identifying User-Agent | Fair use; built for search-as-you-type; debounced 350 ms, minimum 3 characters | 30 days |
| Overpass API | Venue website and email tags | Identifying User-Agent | No parallel queries, back off on 429/406, light daily use | 7 days per (city, venue type) |
| Ollama web search | Last resort for a venue's published email, when its own pages show none (`POST /api/web_search`, 5 results) | Same Bearer key as Ollama Cloud; off with `WEB_SEARCH_ENABLED=false` | Free tier for individuals, higher limits on paid plans; one search per venue without an email | 14 days per query |
| Supabase Auth | Optional sign-in with Google (F12) | Public anon key (browser and API) | Auth rate limits of the plan | No |
| Gmail API | Send one draft from the signed-in user's own Gmail (F12) | The user's Google token (`gmail.send`), per request, never stored | Per-user Gmail sending limits; unverified apps are limited to test users | No |
| Website reader | Brand intake pages; venue emails | None | Robots.txt, timeouts, SSRF guard | 7 days per URL |
| OpenFreeMap vector tiles | Map on results, venue and wizard pages (loaded by the browser, not the API): the "Liberty" style trimmed to food and drink places and famous sights | None; attribution shown on the map | [openfreemap.org](https://openfreemap.org): free, no key, no usage limits | Browser cache |
| OpenStreetMap tiles | Fallback map if OpenFreeMap is unreachable | None; attribution shown on the map | [Tile usage policy](https://operations.osmfoundation.org/policies/tiles/): light use | Browser cache |
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

- `GET {NOMINATIM_BASE_URL}/search?q=<city>&format=jsonv2&limit=5&addressdetails=1&accept-language=en` with `User-Agent: OSM_USER_AGENT`.
- Business location: the same `/search` with `viewbox=<city box>&bounded=1&limit=6`, and `/reverse?lat=&lon=&zoom=18` for a pin dropped on the map. Labels are built from `name` or house number and road; the detail line from neighbourhood, city, state and country.
- One request per second maximum across the whole app (shared limiter), results cached 30 days.
- Called only on an explicit action: pressing Enter or Search (minimum 3 characters), or clicking the map. Never as you type.
- Show "© OpenStreetMap contributors" attribution where OSM data appears.

## Photon

- `GET {PHOTON_BASE_URL}/api?q=<text>&limit=6&lang=en[&bbox=w,s,e,n][&layer=city&layer=district&layer=county&layer=locality]` with `User-Agent: OSM_USER_AGENT`. Default host `https://photon.komoot.io`.
- Fills the dropdown while the user types (debounced 350 ms in the browser, minimum 3 characters). Nominatim forbids autocomplete, so it is never used for this.
- Picking a city suggestion makes one Nominatim city search with the suggestion's full name, for the bounding box the run is limited to.
- Any failure returns no suggestions; Enter still runs the full Nominatim search. Same OSM attribution.

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
- Venue emails (F06): the venue's page plus up to 3 contact-like pages on the same site (contact, then wholesale, catering or events, then about or visit; `/contact` when none is linked). A dead deep link falls back to the homepage, and a query string percent-encoded into the path is repaired. Addresses are read from `mailto:` links (URL-encoded too), plain text, spelled-out forms ("hello [at] venue [dot] com", "hello at venue dot com"), text split across tags, Cloudflare's scrambled email protection, and `"email"` fields in the page's data (schema.org). Kept: the venue's own domain, free-mail inboxes, or another domain that carries the venue's name (cabinjuice@gravityhaus.com). Cached 7 days per URL.
- If no pattern finds an address, one LLM call reads the same pages and must quote the words that show an address. Code checks the quote is on the page and spells that address out, so the AI can find an address but never invent one (CON-05). If the model is unavailable, the result is not cached.
- If the venue's pages, OpenStreetMap and Hunter give no address, one Ollama web search (`"<venue>" <city> email`) runs. Only addresses on the venue's own domain, or carrying its name (cabinjuice@…, yampasandwichco@gmail.com), are kept, with the result page as the source; a directory's other listings are dropped. Stored as source `web`.
- A 403 or a Cloudflare challenge (`cf-mitigated`) means the owner blocks automated readers: we stop and say so ("That site blocks automated readers like ours") and use the description instead. We never work around bot checks.

## Supabase Auth and Gmail (F12)

- Supabase project → Authentication → Providers → Google: enabled with the Google OAuth client. URL configuration: the site URL and redirect URLs must include the web app's origin (`http://localhost:3000/**` locally).
- Google Cloud: the Gmail API enabled, and `https://www.googleapis.com/auth/gmail.send` added to the OAuth consent screen. While the app is unverified, only listed test users can grant it.
- Sign-in asks for `gmail.send` (send only, never read). The API checks a Supabase access token with `GET {SUPABASE_URL}/auth/v1/user` once per sign-in.
- Sending: `POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send` with `{raw}` (the RFC 2822 message, base64url). 401 or 403 means the token expired or the permission wasn't granted; the user reconnects. Google's client secret is not needed: there is no server-side refresh.

## Apollo (optional, disabled by default)

- Only for chains with a purchasing team, behind `APOLLO_ENABLED=true`.
- Not enabled for public demo runs because the app would republish Apollo data to anonymous visitors.
- If enabled, use organisation and people search for the chain's domain and reveal at most one buyer email per chain, with the source shown.

## Failure policy

External services other than Qloo are **non-fatal**: their failure reduces contacts or details but never blocks ranking. Qloo failures are fatal to the scout phase.
