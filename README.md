# Stockist Scout: documentation pack

**Stockist Scout** (working name) is an agent that tells a brand, or the sales rep who sells for it, **which consumer-facing businesses to pitch, which product to lead with, and why**, using Qloo taste data about each business's own customers. It then finds a public business contact and drafts a pitch email that the user approves before anything leaves the app.

Built for the **Qloo Agentic Hackathon 2026** (deadline **Oct 30, 2026, 11:45pm EDT**, which is **Oct 31, 9:15am IST**).

Stack: Turborepo monorepo, **Next.js** frontend (`apps/web`), **FastAPI** backend (`apps/api`), **Supabase** Postgres, **Ollama Cloud** with **Gemma 4 31B** for the agent, Qloo Taste AI, Hunter for business emails, OpenStreetMap (Nominatim and Overpass) for venue details.

## Read in this order

| # | File | What it covers |
|---|---|---|
| 1 | `docs/00-product-brief.md` | Problem, users, value, why Qloo, success metrics |
| 2 | `docs/01-scope.md` | MVP in and out, categories, non-goals |
| 3 | `docs/02-user-flows.md` | End-to-end flows with diagrams |
| 4 | `docs/03-architecture.md` | Monorepo layout, components, data flow, configuration |
| 5 | `docs/features/F01`–`F11` | One file per feature: how it works, inputs, outputs, failures, UI, tests |
| 6 | `docs/04-qloo-integration.md` | Qloo call chain, contract, normalisation, baseline, budget |
| 7 | `docs/05-agent-and-llm.md` | The agent, its tools, Ollama Cloud Gemma 4, prompts, guardrails, portability |
| 8 | `docs/06-data-model-supabase.md` | Tables, SQL, indexes, security, retention |
| 9 | `docs/07-api-spec.md` | FastAPI endpoints and schemas |
| 10 | `docs/08-frontend-spec.md` | Screens, states, components (visuals from `DESIGN.md`) |
| 11 | `docs/09-external-services.md` | Hunter, OpenStreetMap, website reader, optional Apollo |
| 12 | `docs/10-compliance-and-privacy.md` | Outreach rules, opt-out, data handling |
| 13 | `docs/11-plan.md` | Phases and day-by-day schedule to the deadline |
| 14 | `docs/12-acceptance-criteria.md` | Numbered, testable criteria |
| 15 | `docs/13-test-plan.md` | What is tested, how, with which commands |
| 16 | `docs/14-checks.md` | Per-commit, per-phase, pre-demo and pre-submit checklists |
| 17 | `docs/15-evaluation.md` | Qloo-on versus Qloo-off evaluation |
| 18 | `docs/16-runbook.md` | Setup, environment, run, seed, deploy, troubleshooting |
| 19 | `docs/17-judging.md` | Rules, criteria mapping, self-score, hard questions, demo script, Devpost text |
| 20 | `docs/18-risks-and-decisions.md` | Risks, Day 0 spikes, decisions log |
| 21 | `docs/DESIGN.md` | **Placeholder: replace with your design file** |
| — | `AGENTS.md`, `CLAUDE.md`, `START_PROMPT.md` | Instructions for the coding agent and the first prompt |

## How to use this pack

1. Copy the contents of this folder into the root of your Turborepo so `docs/` sits beside `apps/` and `packages/`.
2. If your repo already has an `AGENTS.md`, append this pack's `AGENTS.md` to it instead of replacing it.
3. Replace `docs/DESIGN.md` with your design file.
4. Create `apps/api/.env` from `docs/16-runbook.md`.
5. Paste `START_PROMPT.md` into your coding agent.

## Three rules above everything

1. **Qloo decides who and why.** Every ranking, product match and reason comes from Qloo responses. The LLM writes words and chooses tools; it never invents venues, scores, contacts or facts.
2. **Verify before building.** Every Qloo parameter and response field in these docs is unverified until Phase 0 records it from a live call. The same applies to Ollama tool calling on Gemma 4 Cloud.
3. **Humans approve every email.** The MVP drafts and exports. It never sends email automatically.
