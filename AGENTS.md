# AGENTS.md: TasteRoute

(If the repo already has an AGENTS.md, append this file to it.)

## What this repo builds

TasteRoute, for the Qloo Agentic Hackathon 2026: a Next.js app (`apps/web`) and a FastAPI service (`apps/api`) with Supabase Postgres. It ranks venues for a brand by the taste of each venue's customers (Qloo), picks the best product per venue, finds public business contacts (Hunter, OpenStreetMap), and drafts grounded pitch emails that the user approves. The agent runs on Ollama Cloud with Gemma 4 31B.

Read `README.md`, then `docs/` in numbered order, before writing code.

## Hard rules

1. **Qloo decides; the LLM narrates.** Venue lists, scores, product fit and reasons come from Qloo responses through pure functions in `scoring/`. The LLM chooses tools and writes text only. Reasons are built by templates, not the LLM.
2. **Verify before coding.** Every Qloo parameter and response field is unverified until recorded from a live call (Phase 0). Save fixtures, write `docs/qloo-contract.md`, build models from fixtures. Same for Gemma 4 Cloud tool calling (`docs/llm-contract.md`).
3. **Fail closed on Qloo.** No fallback ranking from any other source outside `APP_ENV=test`.
4. **Humans approve every email.** The app sends only when the user clicks, from the user's own Gmail. No SMTP, no background sending.
5. **Business contacts only, never constructed.** Every stored email has a source. Respect the suppression list and Hunter 451.
6. **Secrets stay server-side.** Keys only in git-ignored `.env`; never logged, traced, returned or bundled. The browser never talks to Supabase, Qloo, Hunter or Ollama.
7. **Provider isolation.** Only files under `apps/api/src/tasteroute_api/llm/` may name an LLM provider. Only `categories/` may name a category.
8. **Respect limits.** Qloo ≤ 4 req/s and the monthly budget; Nominatim ≤ 1 req/s with an identifying User-Agent; Overpass one query at a time; Hunter caps. Cache everything the docs say to cache.
9. **Tests never hit the network.** Use fixtures and respx. Live tests carry `@pytest.mark.live` and never run in CI.
10. **Design.** Read `docs/DESIGN.md` before UI work. If it starts with `PLACEHOLDER`, do not build screens; build client, types and state only, and tell the user.
11. **Honest copy.** "Taste fit", never "will buy". Label inferences.
12. **Scope.** Do not add features beyond `docs/01-scope.md` without asking. Stretch items only after every MVP acceptance criterion passes.

## Working method

- Work phase by phase from `docs/11-plan.md`. Finish and verify a phase before the next.
- Keep `docs/progress.md`: done tasks, passing acceptance IDs (with test names), Qloo calls used, blockers, questions for the user.
- Small commits that reference acceptance IDs, for example `feat(api): baseline lift [RNK-02]`.
- Before each commit, run the checks in `docs/14-checks.md`.
- When live behaviour differs from the docs, trust live behaviour, update the doc, and add a line to the decisions log in `docs/18-risks-and-decisions.md`.
- Ask the user only when blocked on something you cannot decide or obtain (keys, design file, demo brand, demo city choice when Phase 0 is inconclusive).

## Commands

```bash
pnpm install && (cd apps/api && uv sync)
pnpm turbo dev                         # web :3000, api :8000
pnpm turbo lint test build
cd apps/api && uv run pytest -m "not live"
cd apps/api && uv run python scripts/export_openapi.py   # then regenerate packages/contracts
supabase db reset                      # local database from migrations
```

## Code conventions

- Python: typed (mypy strict on `scoring/`, `qloo/`, `agent/`, `grounding.py`), Pydantic v2 models, async httpx, no global mutable state except the shared rate limiters and pools.
- TypeScript: strict mode, types only from `packages/contracts`, no `any` in API code paths.
- SQL: migrations only; snake_case; every user-owned table has `workspace_id`.
- Errors: typed exceptions mapped to problem responses with stable codes (`docs/07-api-spec.md`).
