# 11. Plan

Today is **Mon Oct 19, 2026**. Deadline **Fri Oct 30, 11:45pm EDT (Sat Oct 31, 9:15am IST)**. Target: feature-complete **Tue Oct 27**, submitted **Thu Oct 29**. Times below are IST days.

## Phases and gates

| Phase | Days | Goal | Gate to pass before moving on |
|---|---|---|---|
| 0. Spikes | Oct 19 | Prove Qloo places ranking, baseline, tags, Gemma 4 tool calling, Hunter, Overpass in the demo city | Go/no-go in `18-risks-and-decisions.md` met; `docs/qloo-contract.md` and `docs/llm-contract.md` written |
| 1. Foundations | Oct 19–20 | Scaffold API, Supabase migrations, settings, Qloo client, cache, trace, workspace cookie | Unit and contract tests pass; migrations apply cleanly |
| 2. Scout engine | Oct 20–22 | F02, F03, F04, F05 as tools; deterministic plan; scoring | Fixture run produces ranked venues with evidence; QLO and RNK criteria pass |
| 3. Agent and intake | Oct 22–23 | F01, F09 agent loop with guard and fallback, SSE, trace | Agent and deterministic paths give identical scores; AGT criteria pass |
| 4. Outreach | Oct 23–24 | F06 contacts, F07 drafts with grounding, F08 export and suppression | CON, DRF, EXP criteria pass |
| 5. Frontend | Oct 22–26 (parallel once `DESIGN.md` arrives) | All screens and states | UI criteria pass; keyboard path works |
| 6. Demo and evaluation | Oct 26–27 | Seed demo run, Qloo-on vs off evaluation, deploy | DMO and EVL criteria pass; live URLs work logged out |
| 7. Submission | Oct 28–29 | Video, README, Devpost text, final checks | Pre-submit checklist complete; submitted Oct 29 |
| Buffer | Oct 30 | Fixes only | — |

## Phase 0 tasks (today, about 6–8 hours)

1. Scaffold `apps/api` with `uv`, settings, and `scripts/spike_qloo.py`.
2. **Qloo tags:** find tag ids for café, bar, restaurant, deli, boutique via `/v2/tags`; record them.
3. **Qloo places in the demo city:** for each tag, run insights with location and no signal, then with a demo brand's entities. Record raw responses as fixtures. Note the affinity field, properties (website, address), result counts.
4. **Baseline experiment** (see `04-qloo-integration.md`) and Spearman between with-signal and baseline rankings.
5. **Sensitivity test:** two very different brands (for example specialty coffee versus a mass-market energy drink comparable). Top-20 overlap must be clearly below 100%; target Jaccard ≤ 0.5.
6. **Entity resolution:** 10 small brands and their comparables. Count how many resolve.
7. **Explainability:** find whether a per-venue explanation is available and its cost in calls.
8. **Gemma 4 tool calling:** `scripts/spike_llm_tools.py` sends a two-tool request to Ollama Cloud with the chosen model name; confirm `tool_calls` come back and a tool-result round trip works. Record in `docs/llm-contract.md`.
9. **Hunter:** domain search on 5 real venue domains with the test key, then 2 with the real key.
10. **Overpass and Nominatim:** city bbox, then one café query; count venues with website or email tags.
11. **Choose the demo city** with the best Qloo place coverage and OSM contact coverage.

**Go/no-go:** go if steps 3–5 show meaningful, different rankings with at least 30 venues per main type in the demo city. Otherwise switch city once; if it still fails, stop and reconsider the idea (Crowdspawn pack is the fallback).

## Work breakdown with owners (solo by default)

| ID | Task | Phase | Depends on |
|---|---|---|---|
| T01 | API scaffold, settings, errors, health | 1 | — |
| T02 | Supabase project, migrations 0001, asyncpg pool | 1 | — |
| T03 | Workspace cookie and scoping | 1 | T02 |
| T04 | Qloo client: rate limit, retries, cache, budget, trace, guards | 1 | T02, Phase 0 |
| T05 | Category pack loader and food_drink pack | 2 | Phase 0 |
| T06 | resolve_entities (F02) | 2 | T04 |
| T07 | rank_venues and scoring (F03) | 2 | T04, T05 |
| T08 | match_products (F04) | 2 | T07 |
| T09 | attach_evidence (F05) | 2 | T07 |
| T10 | Deterministic plan + run lifecycle + events | 2 | T06–T09 |
| T11 | LLM provider layer, structured helper, prompts | 3 | Phase 0 |
| T12 | Brand intake (F01) with SSRF guard | 3 | T11 |
| T13 | Agent loop + guard + planner variant + fallback (F09) | 3 | T10, T11 |
| T14 | SSE endpoint with replay | 3 | T10 |
| T15 | Overpass, Nominatim clients, OSM matching | 4 | T02 |
| T16 | Hunter client and contact chooser (F06) | 4 | T15 |
| T17 | Drafts, grounding validator, state machine (F07) | 4 | T11, T09 |
| T18 | Export and suppression (F08) | 4 | T17 |
| T19 | OpenAPI export and contracts package | 3 | T14 |
| T20 | Frontend: wizard | 5 | T19, DESIGN.md |
| T21 | Frontend: live run and results | 5 | T19 |
| T22 | Frontend: venue detail, outreach, trace, settings, sample | 5 | T19 |
| T23 | Demo seed, masking, rate limits, budget guard (F10) | 6 | T18 |
| T24 | Evaluation script and report (`15-evaluation.md`) | 6 | T10 |
| T25 | Deploy web, API; Supabase prod | 6 | All |
| T26 | Video, README, Devpost, LICENSE | 7 | T25 |

## Cut list (if behind schedule, cut in this order)

1. Fashion secondary pack.
2. Email verifier calls (keep domain search only).
3. Regenerate button.
4. Planner variant (keep native tools plus deterministic fallback).
5. Venue detail page (move evidence into an expandable row).

Never cut: baseline lift, evidence, kill switch, grounding validator, human approval, trace page, demo mode.
