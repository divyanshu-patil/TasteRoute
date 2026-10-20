# 18. Risks, Day 0 spikes and decisions

## Risks

| # | Risk | Likelihood | Impact | Mitigation | Spike |
|---|---|---|---|---|---|
| R1 | Qloo place results in the demo city are thin or lack venue-type tags | Medium | High | Choose the city by coverage; keep 4 venue types | S1 |
| R2 | With-signal ranking barely differs from baseline (popularity bias) | Medium | High | Lift formula; sensitivity test; switch baseline method | S2 |
| R3 | Small brands do not resolve | High | Medium | Comparables flow; show which entities were used | S3 |
| R4 | No per-venue explanation endpoint | Medium | Medium | Tag-overlap reasons | S4 |
| R5 | Gemma 4 Cloud tool calling unsupported or unreliable | Medium | Medium | Planner variant, deterministic fallback | S5 |
| R6 | Ollama Cloud rate limits or outages during demo | Low | Medium | Deterministic plan; template drafts; demo run stored | S5 |
| R7 | Few venues have websites or emails in OSM; Hunter finds little | Medium | Medium | Show honest "not found"; choose a city with good coverage | S6 |
| R8 | Hunter free credits run out | High | Low | Cache, cap, demo masking; one paid month if needed | S6 |
| R9 | Overpass public instance overloaded | Medium | Low | Cache per city and type; seed demo early | S6 |
| R10 | Qloo monthly allowance used up | Medium | High | Cache, fixtures in tests, budget guard at 80% | — |
| R11 | Silent 200 responses with ignored filters | Medium | High | Guards on type, radius, tags | S1 |
| R12 | Supabase pooler and asyncpg prepared statements | Medium | Low | `statement_cache_size=0` or direct connection | — |
| R13 | Design file late | Medium | Medium | Backend and types first; UI blocked until it arrives | — |
| R14 | Scope too large for 11 days | High | High | Cut list in `11-plan.md`; no features in the last 48 hours | — |
| R15 | Judges see it as a sales tool, not a taste tool | Medium | Medium | Lead the demo with the taste reasons and the kill switch | — |
| R16 | Outreach misuse (spam) | Low | High | Business contacts only, approval, opt-out, suppression, no sending | — |

## Day 0 spikes (Phase 0)

| ID | Question | Pass condition | Output |
|---|---|---|---|
| S1 | Do tag-filtered place insights with a location work in the demo city? | ≥ 30 venues per main type, correct types, inside the city | Fixtures, tag ids, `qloo-contract.md` |
| S2 | Does the taste signal change rankings? | Top-20 Jaccard between two different brands ≤ 0.5; with-signal vs baseline clearly different | Numbers in `progress.md` |
| S3 | How many small brands resolve, and do comparables resolve? | Comparables resolve for ≥ 8 of 10 brands | Table in `progress.md` |
| S4 | Is there a per-venue explanation and how many calls does it cost? | Known either way | Contract note |
| S5 | Does Gemma 4 Cloud return tool calls through `/api/chat`? | A two-tool round trip works 5 times out of 5 | `llm-contract.md` |
| S6 | Contact coverage: OSM websites/emails and Hunter results for 10 demo venues | Reported numbers; ≥ 4 of 10 with a usable business email is good | Numbers in `progress.md` |

**Go/no-go:** S1 and S2 must pass (after at most one city change). If they fail, stop and switch to the fallback project (Crowdspawn).

## Decisions log (append, never delete)

| Date | Decision | Reason |
|---|---|---|
| 2026-10-19 | Build TasteRoute (taste-based account targeting) | Best sellable idea that keeps Qloo essential; scored about 14.5/20 versus 7/20 for a general sales agent |
| 2026-10-19 | Food and drink is the full category; fashion is secondary if coverage allows | Qloo's strongest place data; specific audience for judging |
| 2026-10-19 | Turborepo, Next.js, FastAPI, Supabase | User's chosen stack |
| 2026-10-19 | Agent on Ollama Cloud with Gemma 4 31B, provider layer for portability | User's choice; native tool calling listed for Gemma 4 |
| 2026-10-19 | Prompt-and-validate JSON, not native schema | Ollama docs: cloud models do not support structured outputs |
| 2026-10-19 | Deterministic tools with a guarded agent and fallback | Identical rankings regardless of the LLM; reliable demo |
| 2026-10-19 | Reasons built by templates from Qloo evidence, not by the LLM | Prevents unsupported claims |
| 2026-10-19 | Drafts and export only; no sending | Compliance, scope, trust |
| 2026-10-19 | Hunter for business emails; Apollo off by default | Domain-based lookups fit venues; avoid republishing Apollo data |
| 2026-10-19 | Anonymous workspaces, no login | Hackathon rule: free, unrestricted testing |
| 2026-10-19 | RLS on, no policies; browser never talks to Supabase | Simple, secure server-only access |
| 2026-10-19 | Fail closed on Qloo; kill switch is a tested feature | Proves the product depends on Qloo |
| 2026-10-19 | D-01 Demo city **Brooklyn, NY**; Qloo location via `filter.location.query=<city>` + `filter.location.radius=0` | Phase 0: 50 venues per type, strict boundary, 82–100% websites. Without `radius=0` results leak into Manhattan |
| 2026-10-19 | D-02 `take` capped at 50 per Qloo call | Live 400 above 50 |
| 2026-10-19 | D-03 Baseline percentile = percentile of Qloo `popularity` within the pool of target ∪ baseline venues for that type (instead of "0 if not in baseline") | Only 10–13 of 50 target venues appear in the baseline top 50, so the old rule made lift ≈ target for most venues. The baseline query is ordered by `popularity`, so this keeps the same meaning for every venue. `not_in_baseline` flag kept ("not among the 50 most popular") |
| 2026-10-19 | D-04 Coverage notice when fewer than 15 venues survive or the baseline returns fewer than 15 (overlap rule dropped) | Overlap is structurally low (D-03) |
| 2026-10-19 | D-05 F04 per-product queries use `filter.results.entities=<ranked venue ids>` | Every ranked venue gets a real per-product percentile; "missing = 0" no longer needed |
| 2026-10-19 | D-06 Evidence uses `feature.explainability=true` on the target call (0 extra calls) plus one `filter.type=urn:tag` audience-taste call per run, intersected with venue tags | Qloo has no per-venue explanation endpoint; these two give grounded reasons |
| 2026-10-19 | D-07 Planner variant cut (cut list #4) | Native tool calls on `gemma4:31b` passed 5/5 with a "one tool per turn" prompt; deterministic fallback kept |
| 2026-10-19 | D-08 Contacts: Qloo `website` → venue's own site published email (`source=website`) → OSM email → Hunter (when `HUNTER_API_KEY` is set) | No Hunter key yet; OSM emails 4/50, own-site emails 3/12 in the spike. Emails are only ever copied from a page, never constructed |
| 2026-10-19 | D-09 Local Postgres 15 + `scripts/migrate.py` applying `supabase/migrations/*.sql` | Supabase CLI and Docker not available; the same SQL applies to Supabase when the user adds `DATABASE_URL` |
| 2026-10-19 | D-10 Demo brand is a fictional Brooklyn drinks maker entered by description; its products resolve through real comparables | Avoids implying a real brand endorses the public demo; still exercises the small-brand → comparables path |
| 2026-10-19 | D-11 Live rules (read 2026-10-19): demo video **not** required; an externally hosted demo **is** required; licence visible in repo About | Devpost overview and rules pages |
| 2026-10-19 | D-12 Gemini adapter not built; provider layer has Ollama Cloud + Fake | Not needed for the demo; adding one is a new file under `llm/` |
| 2026-10-19 | D-13 Confidence `support` = number of signal entities whose explainability score is at least half their fair share (≥ 0.5/k); `high` needs support ≥ 2 | Qloo explainability is per signal entity; a match driven by one comparable is weaker evidence |
| 2026-10-19 | D-13a `high` needs support ≥ min(2, brands in the signal) | End-to-end run with a brand Qloo knows by itself (one signal entity): no venue could ever be `high` |
| 2026-10-19 | D-14 Café venue type uses only `urn:tag:category:place:coffee_shop` | Verified in Phase 0; OR semantics of several `filter.tags` values are unverified |
| 2026-10-19 | D-15 Contact chooser order (refines D-08): verified role Hunter → verified generic Hunter → OSM email → venue-site email → unverified Hunter; invalid or disposable never used | Prefer verified, then public listings, then the venue's own page |
| 2026-10-19 | D-16 Fixture mode serves recorded Qloo responses by normalised params, with two documented synthetic cases: unknown `/search` name → no results; per-product `filter.results.entities` → recorded places with a deterministic affinity | Per-product calls cannot be pre-recorded for every product combination; tests still never touch the network |
| 2026-10-19 | D-17 Reasons quote crowd and interest tags but never sensitive identity tags; audience tags shared by more than half the ranked venues are dropped as non-distinctive | Avoids profiling language and generic reasons ("Restaurant") |
| 2026-10-20 | D-18 Client IP is the X-Forwarded-For entry `TRUSTED_PROXY_HOPS` from the right (1 on Render), else the socket peer; confirm on the host with the runbook's debug log | A spoofed left-most entry can't dodge the per-IP run cap |
| 2026-10-20 | D-19 An interrupted outreach goes back to `scouted` (keeps the ranking), an interrupted scout to `failed`, after 15 minutes without events | Results stay visible; nothing is left "running" forever |
| 2026-10-20 | D-20 The AI email reader is removed: an address counts only when the page parser reads it exactly; web search pages are fetched, not trusted as snippets | "Never constructed" must be provable; a model that assembles an address from parts is a guess |
| 2026-10-20 | D-21 Workspace deletion deletes the runs' LLM and web call logs but keeps Qloo call rows without content | Privacy promise kept without letting a delete reset the monthly Qloo budget |
| 2026-10-20 | D-22 The postal address lives in the brand profile JSON, not a new column | No migration; profile already round-trips through the wizard |
| 2026-10-20 | D-23 Lift = taste percentile minus the same venues' percentile under mass-market brands (Coca-Cola, Pepsi, Budweiser, Starbucks, Dunkin'), not a separate popularity query; popularity kept for display; old runs keep their stored numbers | Lift should be a taste claim about the same venues ("guests here like brands like yours more than mass-market brands"), not a comparison with a different set of popular venues. Measured on two runs: both lifts change a third to half of the top 15 vs taste alone and agree with each other on about half (`docs/evaluation-results.md`) |
| 2026-10-20 | D-24 Best product = highest z-score of each product's affinity across the type's ranked venues; clear needs z-gap ≥ 0.75 and raw gap ≥ 0.01, close ≥ 0.25 | Percentiles over 0.03-wide affinity bands turned noise into "clear" picks |
| 2026-10-20 | D-25 Buyability flags never change scores: chains and venues of brands in the signal rank after the rest and are hidden by default (counted, warning names them); makers of what you sell get a chip; a café, deli or bakery leads with a non-alcoholic product when one was scored, else "check licence" | A founder can't pitch Starbucks or a rival roaster; the list should be actionable |
| 2026-10-20 | D-26 "Rising (Qloo)" only when `audience_growth` > 0 (most venues read 0, scale undocumented), not "top quartile" | With most values 0, a quartile rule would mark ordinary venues as rising |
| 2026-10-20 | D-27 Reasons say "Known for X, which fans of Y over-index on" | The overlap tags are what the brands' fans over-index on, not scores of the venue's guests; the old "guests here over-index" overclaimed |
| 2026-10-20 | D-28 Stockist backtest pool = Qloo's 500 best-known venues per type; an account counts only if it is in the pool | The pre-registered pool (top-50 lists plus accounts found by search) picked accounts and non-accounts differently and ranked accounts below random for every Qloo method on the dev brands; found and fixed before the test run |
| 2026-10-20 | D-29 Keep fit as it is and show an LLM's ranking next to it ("Compare with an LLM"), not a hybrid | The backtest is a tie: Qloo and the LLM find different accounts. Changing the ranking after seeing the test would be tuning on the test. Open: drop the brand's own category from the mass-market set (Starbucks and Dunkin' pushed café accounts down for a coffee roaster); needs new brands to test |
