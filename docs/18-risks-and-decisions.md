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
| 2026-10-19 | Build Stockist Scout (taste-based account targeting) | Best sellable idea that keeps Qloo essential; scored about 14.5/20 versus 7/20 for a general sales agent |
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
