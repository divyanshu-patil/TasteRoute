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

`uv run pytest -m "not live"`: 99 passed, 91% coverage (scoring 96–100%, qloo 86–100%, agent 81–100%, grounding 100%). `ruff` and `mypy` clean. No network in tests (respx, recorded fixtures, `FakeProvider`, local `stockist_test` DB).

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

## Budget used

| Service | Calls |
|---|---|
| Qloo | 44 live (37 × 200, 7 × 400 while learning `take` limit and shell quoting); 0 in tests |
| Ollama Cloud | ~20 (spike) |
| Nominatim / Overpass | 1 / 1 |
| Hunter | 0 (no key) |

## Blockers / needed from the user

- `HUNTER_API_KEY` (optional; contacts work without it, see D-08).
- Supabase `DATABASE_URL` (using local Postgres until then).
- Hosting accounts for the required public demo (web on Vercel, API on Render/Railway/Fly).
