# Progress

## Phase 0: Spikes — done 2026-10-19

| Spike | Result |
|---|---|
| S1 Qloo places in Brooklyn | Pass: 50/type (café, bar, restaurant, deli), 100% tagged, 82–100% with website |
| S2 Taste signal changes ranking | Pass: brand-vs-brand top-20 Jaccard 0.176 (café), 0.212 (bar); target vs baseline 0.08–0.21, Spearman −0.17 |
| S3 Resolution | Pass: comparables 9/9; small brands 2/7 self-resolve |
| S4 Explainability | Available on the same call; plus audience tag insights (1 call) |
| S5 Gemma 4 tool calling | Pass: 5/5 round trips on `gemma4:31b` (Ollama Cloud) |
| S6 Contacts | OSM match 30/50, OSM email 4/50; own-site email 3/12; Hunter blocked (no key) |

Go/no-go: **GO**, demo city Brooklyn. Contracts: `docs/qloo-contract.md`, `docs/llm-contract.md`.

## Phases 1–4: API, scout engine, agent, outreach — done 2026-10-19

`uv run pytest -m "not live"`: 99 passed, 91% coverage (scoring 96–100%, qloo 86–100%, agent 81–100%, grounding 100%). `ruff` and `mypy` clean. No network in tests (respx, recorded fixtures, `FakeProvider`, local `tasteroute_test` DB).

| Area | IDs passing | Tests |
|---|---|---|
| Data | DAT-01, DAT-02, DAT-03 | `scripts/migrate.py`, `test_rls_enabled_without_policies`, `test_other_workspace_gets_404` |
| Qloo | QLO-01..06 | `test_scout_run_end_to_end`, kill switch (key missing, 401), `test_qloo.py`, `test_clients.py` |
| Intake | INT-01..05, CAT-01..03, SEC-02 | `test_intake_paths`, `test_read_site_page_and_text_caps`, SSRF unit tests, grep test |
| Entities | ENT-01..05 | `test_resolve_uses_qloo_ids_only`, `test_add_entity_from_qloo_search`, name matching |
| Ranking | RNK-01..06, FIT-01..03, EVD-01..03 | crafted lift fixture, confidence boundaries, end-to-end run, `test_failed_product_query_…` |
| Agent | AGT-01..06, LLM-01, LLM-02, LLM-04, LLM-05 | plan guard, step limit, text twice, provider down, identical scores, SSE replay, trace |
| Outreach | CON-01..07, DRF-01..06, EXP-01..04, REL-03 | validator cases, template fallback, state machine, flow test, Hunter 451/cap, suppression |
| Demo/limits | DMO-01..05, SEC-03, SEC-04, API-02, REL-01, REL-02 | masking, read-only sample, per-day limit, search rate limit, retries |

Notes: LLM-03 (Ollama Cloud without local Ollama) verified in Phase 0 spike. DMO-04 is covered by the LLM cap (agent hands over to the deterministic plan, results kept); a Qloo per-run cap fails the phase closed, like the kill switch.

## Phase 5: Frontend — done 2026-10-19

All 11 routes in `08-frontend-spec.md` built on `DESIGN.md` (Anton/Inter/JetBrains Mono, canvas #e5e5e5, white 24–32 px cards, inverted black, mint tags, yellow emails, no shadows). Types come from `packages/contracts` (generated from the API's OpenAPI). `pnpm turbo lint check-types test --filter=web`: clean, 9 Vitest tests.

| ID | Evidence |
|---|---|
| UI-01 | Visual review of every screen at 1440 px and 390 px against `DESIGN.md`; screenshots in `docs/screenshots/` |
| UI-02 | All 11 states reachable: skeletons, SSE live steps with Qloo counter (live vs cached), warnings, Qloo error panel with retry and no partial table, LLM-unavailable banner and "template" drafts, unsupported-business panel, low-coverage notice, "No public business email found" with sources checked, empty filter with "Clear filters", offline banner with `Last-Event-ID` replay, 404 |
| UI-03 | Fit, lift, confidence and every stat card have tooltips; reason markers render as "Qloo" / "Our inference" chips that link to the trace |
| UI-04 | Lighthouse accessibility 95–100 on 7 pages (only remaining flag was `#979797` text, now darkened); skip link, visible focus, tooltips on focus; no horizontal scroll at 390 px |
| UI-05 | `lib/copy.test.ts` greps all UI source for "will buy" / "demand" |

Unit tests: progress reducer (replay ignored, failures), formatting, source-chip rendering, copy grep.

## Phase 6: Demo and evaluation — in progress 2026-10-19

| ID | Status |
|---|---|
| DMO (seed) | Sample run re-seeded with live calls after the name-matching fix (Health-Ade Kombucha now resolves). Agent ran both phases; 60 venues; 4 of 8 top venues have a public email; all 4 drafts LLM-written with cited Qloo evidence. `/v1/demo` serves the newest demo-workspace run, so no env change is needed locally. |
| EVL-01 | `scripts/evaluate.py` → `docs/evaluation-results.md`. Two brands (specialty coffee vs mainstream cola). Brand overlap 0.00, A vs popularity 0.00, A vs no-Qloo 0.00 (pool effect stated: only 1 of A's 15 was in C's OSM pool). Metric 3 (blind pairs, `docs/evaluation_pairs.csv`) and metric 4 (reason checks) wait for a human judge. |
| Deploy | Waiting on hosting accounts and a Supabase `DATABASE_URL`. |

## Phase 7: Submission — in progress 2026-10-19

Done: README (hero and drawn flow in `assets/readme/`, real screenshots), MIT `LICENSE`, `docs/devpost.md`, CI (`.github/workflows/ci.yml`), Render blueprint (`render.yaml`). Project renamed to TasteRoute (package `tasteroute_api`, local DBs `tasteroute` / `tasteroute_test`).

Claims audit and end-to-end check: every judge-path step passes over HTTP (`scripts/e2e_smoke.py`, run 9c15f088). Passing: SEC-01 (secret scan clean), API-01 (contracts current; CI now fails on drift), QLO-07, LLM-06, REP-01, REP-02 (architecture diagram added to the README), REP-03 (clean clone). Fixed on the way: contact choice prefers the venue's own sales or main inbox and drops placeholder, script-embedded and other-domain emails (CON-03, CON-05); brand name read from the site's title (INT-01); a one-brand signal can reach high confidence (FIT-02, D-13a); comparables must fit the product, so "Bubbies" no longer matches "Bubbies Ice Cream" (ENT-03); city search returns 503 when Nominatim is down (REL-01); tests refuse non-loopback sockets (SEC-01). Docs corrected: the grounding validator checks names, numbers, evidence ids, the venue name and the opt-out line, not general claims.

Added at the user's request: a venue map on results and venue detail (now MapLibre with OpenFreeMap vector tiles: a colourful map that shows only food and drink places and famous sights; numbered rank pins) and a guided tour of the sample run (`?tour=1`, results → venue → outreach → trace). Then the business location: search inside the city or click the map (plain-English labels from Nominatim with `accept-language=en`, bounded to the city box), a mint "You" pin, km per venue, a "Nearest to you" sort and distance on venue detail. Ranking is unchanged. Suggestions now appear as you type, from Photon (built for search-as-you-type; Nominatim forbids it, so Nominatim runs only on Enter, a map click, or once when a city suggestion is picked). The location picker is also on step 1, the step 4 map shows before a city is chosen, and the chosen city is framed with a dashed outline. `PUBLIC_RUNS_PER_IP_PER_DAY=0` turns the daily run limit off locally. 126 API and 19 web tests pass. Not built: DAT-04 (stretch cleanup script).

Outreach controls (user request): "Find contacts & draft" opens the outreach page at once instead of waiting on "Starting…"; Cancel replaces Clear and stops the outreach on the API (`POST /v1/runs/{id}/cancel`, keeps what was found, also frees a run stuck by an API restart); "Select all shown" picks the visible rows (max 25). F06. Then: the select-all box sits in the table header (a row above the table at phone width); the outreach page shows live progress over the existing SSE stream (new `venue` event per venue: spinning active step, k-of-n bar, the venue being checked, results as they land, contacts and drafts refreshed as each finishes, counters for the outreach phase only); the contacts box stays hidden until the first venue is checked; "venue website" links to the site. Email finding (user request): every contact-like page is read (not only when the homepage has none); spelled-out, split, URL-encoded, Cloudflare-scrambled and schema.org addresses are found; dead or mangled venue links fall back to the homepage; an address on the owner's domain that carries the venue's name is kept; and when nothing matches, one LLM call reads the pages and must quote the address, which code checks against the page (never a guessed address). On the Colorado run this found addresses for WoodGrain (catering@, a Gmail inbox) and Cabin Juice; Yampa and The Woods only have contact forms. Then (user request): Ollama web search as the last resort when nothing else finds an address (same key, `WEB_SEARCH_ENABLED`, cached 14 days, migration `20261020000000_web_search.sql`); only the venue's own-domain or name-bearing addresses are kept, shown as "web search" with a link to the page. F12 (user request): optional sign-in with Google through Supabase Auth ("Log in to save progress"; work done before signing in joins the account, also from a second device) and one-click "Send with Gmail" per draft from the user's own Gmail (`gmail.send`; the Google token stays in the browser and is never stored; a sent draft is final; EXP-04 reworded). Migration `20261020010000_accounts.sql`. ACC-01..03 pass. Supabase's hosted database is reachable through the pooler; migrations to it still need to be applied. Nav: "Log in to save progress" (white, like the nav; "Log in" on phones), "Start a run" removed from the nav, "My runs" renamed "All runs" (user request); `scripts/claim_runs.py` moves pre-login runs on your own database into the account. App icon and favicon (user request): black square, yellow route from a start dot to a mint pin (`app/icon.svg`, `favicon.ico` 16/32/48, `apple-icon.png` 180), also on the docs site. Privacy policy and terms of service (user request) at `/privacy` and `/terms`, linked from the footer, written from what the code does (Gmail send-only and Limited Use statement; no analytics; data kept until deletion is asked for, because no 60-day cleanup runs yet). Send all (user request): one button in the export bar sends every unsent draft after a confirm step, one at a time through the same send route; waits while a draft has unsaved edits; stops on a Gmail reconnect (ACC-04). Google OAuth verification feedback (user request): privacy policy rewritten around Google user data (access, use, sharing, storage and protection, retention and deletion, Limited Use, no AI training); self-serve "Delete account and data" (`DELETE /v1/workspaces/me`, also removes the Supabase user; ACC-05); `GOOGLE_SITE_VERIFICATION` puts Search Console's tag on every page.

Production sample fix (2026-10-20): the Vercel build had `NEXT_PUBLIC_API_URL` set to the site itself, so every API call (and `/sample`) hit a 404, and the MapLibre worker was missing because `public/maplibre` is only made on install. The web build now copies the worker and refuses to build on Vercel when the API URL is missing, localhost or the site's own host; `/sample` says "Can't reach the TasteRoute API" with a retry instead of "isn't available". `render.yaml` adds `DB_STATEMENT_CACHE_SIZE=0` (Supabase pooler), `CORS_ORIGINS` and the sign-in variables. `scripts/copy_demo_run.py` copies the sample run (0 Qloo or LLM calls) into another database; run 8620b326 is now in the hosted Supabase database and served correctly by a local API pointed at it. Still needed: the API deployed (Render) and `NEXT_PUBLIC_API_URL` set on Vercel.

Open: public deploy of the API (Render; Supabase database is ready), demo video, a cited wholesale figure for the Devpost text, blind-pair judging (metric 3) and reason checks (metric 4).

## Score plan Phases A–B — done 2026-10-20

Phase A (demo safety): client IP from the trusted proxy hop, global daily run cap with a link to `/sample`, Qloo budget gate and per-IP limit on resolve and search, atomic per-run Qloo cap, Retry-After, interrupted runs closed on start, no production boot with the default secret, fetches pinned to the checked IP with one deadline, 10-minute per-run SSE token, opt-in uptime workflow. SEC-05..SEC-10, QLO-08, REL-04..REL-08 pass.
Phase B (every claim true): sending needs an approved draft (DRF-07, ACC-06); the validator checks whole-number tokens, a claim blocklist and evidence quotes in taste sentences (DRF-08); addresses only when the parser reads them on a fetched page, free-mail only when labelled and ranked lower (CON-08); outreach evidence links its external call, no duplicates (EVD-04); deletion removes run logs (REP-06); optional postal address in the signature (DRF-09). Pitch pass rate after the stricter validator (`scripts/draft_pass_rate.py`, run 386c7d86, 8 venues, three prompt rounds): 8/8 first pass every round, 0 repairs, 0 templates.

## Score plan Phases C–D — done 2026-10-20

Phase C (ranking that means what it says): lift against the same venues' taste for mass-market brands (D-23; old runs keep their numbers), best product by standardised affinity (D-24), chains and venues of brands you resemble hidden and counted, maker and licence flags, a café leads with a non-alcoholic product (D-25), Rising (Qloo) (D-26), plain reasons (D-27), insights paging verified to page 10. Measured: lift changes a third to half of the top 15 vs taste alone (`scripts/lift_effect.py`). RNK-07..10, FIT-04, EVD-05, QLO-10 pass.
Phase D (stockist backtest): pre-registered, then six real brands' published Brooklyn accounts (`scripts/fetch_stockists.py`, `docs/eval/stockists.csv`), one pool per brand from Qloo's 500 best-known venues per type, Q-fit / Q-raw / POP / LLM rank the same pool (`scripts/evaluate_stockists.py`). The dev run caught a pool biased against Qloo; fixed and recorded before the test run (D-28). **Result: target missed.** Q-fit beat the LLM on recall@30 in 1 of 3 scored test brands, tied 1, lost 1; Steven Graf Wine not scored (Qloo knows none of its comparables). Top 30 over 47 accounts: Q-fit 8, LLM 8, Q-raw 10, chance 1.5. Published in `docs/evaluation-stockists.md`, `/evaluation`, README and Devpost. "Compare with an LLM" on results (`POST /v1/runs/{id}/llm-ranking`, LLM rank column, "Only TasteRoute ranks this high" badge; precomputed in `seed_demo.py`). EVL-02..06, UI-06 pass. Blind pairs (`docs/evaluation_pairs.csv`) still need a human judge.

## Score plan Phases E–F — done 2026-10-20

Phase E (music taste from Qloo): probed first (artists and podcasts for the comparables' fans, a venue as signal, venues scored by artist fans; 4 calls, `docs/qloo-contract.md`). Every ranked venue gets a `qloo_cross_domain` item, a reason clause for the top quarter of its type, a "Shared tastes beyond food and drink" card and a pitch hook. The pre-registered backtest check failed (Q-fit+C 4 test accounts in the top 30 vs Q-fit 8), so music never changes fit (D-30). EVD-06, QLO-09 pass. E3 (routes) not started.
Phase F (agent decisions): prompt v3 gives a goal, tools and rules, not a plan; tool results carry the numbers; new tools `suggest_more_comparables` and `add_venue_type` with stated reasons; the plan guard checks safety, not equality; the fixed plan applies the same rules; "Decision" rows in the trace and live log (D-31). F7, three live runs (`scripts/agent_decisions.py`, `docs/eval/agent-decisions.json`): Hudson, NY hot sauce: the agent added cafés, then restaurants (8 → 21 venues); Brooklyn natural-wine importer: the agent asked for more similar brands for both wines, one round each where the rule allows two, and Qloo confirmed none, so the run failed closed; Portland, Maine coffee: no decision needed (60 venues). So each decision fired in 1 of 3 runs. The runs also found and fixed two bugs: "Portland" landed in Oregon (D-32, QLO-12) and "chipotle sauce" resolved to the Chipotle chain (D-33, ENT-06); and an LLM time-out showed the fixed plan adding the same types. AGT-07..09 pass.

## Score plan Phase G (states and polish) — in progress 2026-10-20

G1 `.pfit` was already separate from `.bar` (UI-07). G2 map (UI-08): a "Skip map" link, pins focus in rank order with rank 1 drawn on top, the 50 dots are out of the tab order, dots have a 24 px target (checked in headless Chrome: pins 1–10 then "You", 0 focusable dots, dot 24 px). G3 error states (UI-09): results venues, `/runs` and an unknown venue show an error with Retry or a back link; `/start` already mapped a bad URL. G4: tooltips for clear, close and tie; the Orchestration card says "An AI agent chose each step; a rule checker approved every call". G5: the venue page overflowed by 7 px at 360 px because the evidence grids sized to the map attribution; fixed with `minmax(0, 1fr)` columns; 9 pages now measure 360 px wide with no wider element. G6: Lighthouse on a local production build (`docs/lighthouse/`): accessibility 100 on 6 of 7 pages and 96 on results (overlapping map pins, `target-size`); performance 79–96; best practices 100. It found pins whose names lacked their visible text ("You", the rank), now fixed. Rerun on the hosted demo once deployed. G7 needs hosted runs.

## Score plan Phase H (sample, docs) — in progress 2026-10-20

H1: new sample run `7892878f` (`seed_demo.py --outreach 15`, agent orchestration). Founder test passed: the top 10 has no chains, no comparable-brand venues and no alcohol pick at a café or bakery; every venue has music evidence; the LLM column is filled and 4 of the top 10 carry "Only TasteRoute ranks this high". Contacts for 12 of the top 15. Reading the drafts found two problems, fixed at the root: the grounding validator kept "Co." with its period in the allowed words but stripped it from the draft, so every draft for a brand name ending in "Co." failed and needed a repair call (OUT tests: `test_validator_accepts_a_brand_name_ending_in_a_period`); and the bundle handed the model a product kind its name already says ("our Nitro Cold Brew cold brew coffee"; `kind_unless_named`). Redrafting the sample now takes 12 LLM calls, all grounded first time, against 24 before. The sample's sender is "Sam" (was "Sam at Fieldnote", which gave "I'm Sam at Fieldnote from Fieldnote Drinks"). The hidden-venues warning leaves out zero counts. Not yet copied to the hosted database (needs the user's deploy).
H2: README updated (agent decisions, music taste, test counts 165 API and 21 web, coverage table, contacts, hero and flow images with the new sample and the current lift definition). `evaluate.py` setup A now uses mass-market lift like the app (it still used the popularity baseline); rerun: A vs popularity-only 0.07 and 0.00, A vs no-Qloo 0.00 and 0.00, the two brands share 1 venue (was 0). Blind pairs regenerated (none were filled).
H2a: the sample brand in Brooklyn, Chicago and Los Angeles (`scripts/coverage_cities.py`, `docs/eval/coverage-cities.json`): 60 venues each; high confidence 12, 15, 14; top 10 with a published contact 9, 8, 8.
H2b: tour steps for the LLM column, the shared-tastes card and `/evaluation` (the trace tour now ends there; `/evaluation` gained "Start your own run"); screenshots retaken from a local production build; 5 Devpost gallery images (3:2) in `docs/screenshots/devpost/`.
H3: Devpost: cited figures (Eightx, June 2026; ACSA and Park Street, October 6, 2026, newer than the figures in the plan: 2,131 distillers), try-it line, cross-domain step, path to use with measured calls per run, how it's different, Lighthouse line.

## Score plan E3 (taste route) — done 2026-10-20

Probed first (3 calls, `docs/qloo-contract.md`): the heatmap needs a signal; the brand and mass-market heatmaps differ (Spearman 0.14). `POST /v1/runs/{id}/route` makes two heatmap calls, groups the top 15 into walkable areas, orders them by heatmap lift and stores the result (`runs.route`, new migration); `GET` returns it without calls. Results page: a "Taste route" card with the areas and their walks, a heatmap layer and per-area dashed walks on the map, a tour step; "Plan a taste route" on live runs. Sample: 7 areas, Bushwick first (+80), Carroll Gardens 8 venues on a 3.5 km walk; 2 Qloo calls. QLO-11 passes (D-34). Lighthouse rerun on the new sample: accessibility 100 on all 7 pages, performance 87–96.

## Hosted timing and end-to-end check (G7, H4) — 2026-10-20

`scripts/e2e_smoke.py` now prints the machine time from the description to ranked results, and has `--scout-only`. Against the hosted API:
- **Full run (Brooklyn, pickle brand):** 33 of 34 checks passed. The failure was the script's own out-of-date check: `/health` says "configured" until a live Qloo call succeeds within 15 minutes (REL-04); the script now accepts it. To ranked results: 144 s (intake 3, Qloo matches 18, scout 123), via the agent; outreach for the top 6: 66 s, 3 of 6 with a public email and 3 drafts. Run `e9b40ca1`.
- **Scout-only run (Chicago, coffee brand):** 120 s (intake 2, Qloo matches 17, scout 101). Run `ff56e335`.
- **Third run (Los Angeles):** refused with 429 by the per-IP limit of 3 live runs a day. Earlier runs from the same network count toward it.

The landing page said "about 90 seconds"; it now says "about 2 minutes". Calls: Qloo 26 live (12 + 14) and 17 cached, LLM 23 plus the third run's intake and Qloo matches (about 4), 24 page fetches, 2 Overpass.

## Heatmap backtest check — 2026-10-20

Pre-registered in `docs/15-evaluation.md` ("Taste heatmap", commit `f242ab2`) before it ran. Q-fit+H (the mean of the Q-fit and heatmap-lift positions) put 6 test accounts in its top 30, against 8 for Q-fit and 8 for the LLM, and 0 of Kings County Distillery's against Q-fit's 2. **The rule failed:** the heatmap stays a route and a map layer and never changes fit. Published in `docs/evaluation-stockists.md`. The route's lift calculation is now shared with the check (`route.lift_cells`, `route.lift_at`). 5 live Qloo calls (the brands' heatmaps; the mass-market heatmap was cached), no LLM calls.

## Hosted demo — 2026-10-20

https://taste-route.vercel.app with the API at tasteroute.onrender.com. Main pushed (`6a79362`); both redeployed. The hosted database already had the new columns; the sample run `7892878f` was copied there (`copy_demo_run.py`, no Qloo or LLM calls), and `/v1/demo` serves it (`DEMO_RUN_ID` is empty, so the newest demo run wins). `/sample`, `/evaluation`, results with the taste route and heatmap, venue, outreach and trace load. G6 on hosted: accessibility 100 on all 7 pages, performance 65 (results) to 98 (`docs/lighthouse/`). Still open: G7 timing (3 live hosted runs), H4 hosted e2e and one live run, and the uptime workflow (repository variables, the owner's call); the API is on Render's free plan, which sleeps after 15 idle minutes.

## Budget used

| Service | Calls |
|---|---|
| Qloo (score plan C–D) | 445 live: 5 probes (place search, page 5, page 10), 6 lift measurement, 4 baseline-brand searches and 1 paging probe, 429 stockist backtest (dev runs 170 + 64 + 35, test 150, re-runs cached) |
| Qloo (hosted e2e and timing) | 26 live, 17 cached, plus the refused third run's matches |
| Qloo (heatmap backtest check) | 5 live (433 cached) |
| Qloo (score plan E3) | 5 live: 3 heatmap probes, 2 for the sample's route |
| Qloo (score plan G–H) | 40 live: 9 sample reseed, 27 coverage cities (Brooklyn mostly cached), 4 mass-market readings for `evaluate.py` |
| Ollama Cloud (score plan G–H) | 166: 36 sample reseed, 36 two redrafts of the sample, about 82 coverage cities and wizard, 12 `evaluate.py` setup C |
| Web (score plan G–H) | 110 venue pages, 22 web searches, 2 Overpass, 1 Nominatim |
| Qloo (score plan E–F) | 204 live: 4 cross-domain probes, 2 city probes, 100 music check in the backtest, 98 agent decision runs (5 brands' wizards and 8 runs while fixing bugs found in them) |
| Ollama Cloud (score plan E–F) | 109: 55 agent steps, 36 comparables, 17 brand profiles, 1 repair |
| Ollama Cloud (score plan D) | 178: 177 backtest LLM rankings (cached in `docs/eval/llm/` for re-runs), 1 sample LLM ranking |
| Qloo | 128 live: 44 Phase 0 spikes (7 × 400 while learning the `take` limit), 25 first seed, 9 re-seed, 8 evaluation (re-run fully cached), 42 claims audit and end-to-end runs; 0 in tests |
| Ollama Cloud | ~181: ~20 spike, ~20 first seed, 20 re-seed, 12 + 12 evaluation, 11 sample outreach refresh, 62 audit and end-to-end runs, 24 draft pass-rate (score plan B2) |
| Venue websites | 27 live in the local DB (seed, contact fixes, end-to-end runs) |
| Nominatim / Overpass | 7 / 5 live in the local DB (5 for the location picker: 4 via `scripts/place_probe.py`, 1 from a step 1 screenshot check) |
| Photon | 4 live, all via `scripts/place_probe.py`; screenshot checks hit the cache |
| Hunter | 0 (no key) |

## Blockers / needed from the user

- `HUNTER_API_KEY` (optional; contacts work without it, see D-08).
- Supabase `DATABASE_URL` (using local Postgres until then).
- Hosting accounts for the required public demo (web on Vercel, API on Render/Railway/Fly).
