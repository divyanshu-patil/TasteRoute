# 13. Test plan

## Test layers

| Layer | Tools | Network | Runs in CI | What it proves |
|---|---|---|---|---|
| Unit | pytest | None | Yes | Scoring maths, guards, matching, validators, state machines, encoders |
| Contract | pytest + recorded fixtures | None | Yes | Qloo, Hunter, Overpass, Nominatim and Ollama responses parse with our models; silent-failure guards |
| Integration | pytest + respx + test database | None (DB local) | Yes | Clients (rate limit, retries, cache, budget, trace), tools, agent loop with `FakeProvider`, repositories |
| API | FastAPI TestClient/httpx + `FakeProvider` + fixtures + test database | None | Yes | Endpoints, validation, SSE, workspace scoping, kill switch, demo mode |
| Frontend unit | Vitest + Testing Library | None | Yes | Components, hooks, formatting, SSE reducer |
| End-to-end | Playwright against API in fixture mode (`APP_ENV=test`) | None to third parties | Yes | Flow A from intake to export, Flow C sample, error states |
| Live smoke | pytest `-m live` | Real APIs | **No** (manual) | One real run in the demo city; proves keys and contracts |
| Evaluation | `scripts/evaluate.py` | Real APIs (cached) | No | Qloo-on vs Qloo-off quality (see `15-evaluation.md`) |

## Fixture mode

`APP_ENV=test` swaps every external client for a fixture-backed fake (respx routes loading files from `apps/api/tests/fixtures/<service>/`). Fixtures are recorded with `scripts/record_fixture.py` during Phase 0 and later, keys stripped. A missing fixture fails the test loudly (no silent network access in tests).

## Test database

- Preferred: Supabase local (`supabase start`, Docker) and `supabase db reset` before the integration suite.
- Without Docker: a dedicated Supabase cloud project for tests, with `TEST_DATABASE_URL`; the suite truncates tables between tests. Never point tests at production.

## Commands

```bash
# API (from apps/api)
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -m "not live" --cov=stockist_api --cov-report=term-missing
uv run pytest -m live -k smoke            # manual only, spends real calls

# Web (from repo root)
pnpm --filter web lint
pnpm --filter web typecheck
pnpm --filter web test
pnpm --filter web exec playwright test

# Whole repo
pnpm turbo lint test build
```

Coverage targets: 85% for `scoring/`, `qloo/`, `agent/`, `grounding.py`; 70% overall for the API.

## Test matrix (feature → tests → acceptance IDs)

| Feature | Key tests | IDs |
|---|---|---|
| F01 Intake | SSRF guard cases; page selection; text cap; profile parse/repair/fallback; unsupported detection | INT-01..05, SEC-02 |
| F02 Entities | Name normalisation; LLM names never become ids; cache; type guard | ENT-01..05, QLO-04, QLO-06 |
| F03 Ranking | Percentile, lift, fit; crafted fixture where lift reorders; confidence boundaries; radius/type guard; rescore without calls | RNK-01..06, QLO-01..05 |
| F04 Product fit | Margin labels; missing venue = 0; one failed product | FIT-01..03 |
| F05 Evidence | Every venue has reason; evidence ids exist; inference labels; stale flag | EVD-01..03 |
| F06 Contacts | OSM match; domain extraction and skip list; chooser order; 451; 202 polling; cap; no constructed emails | CON-01..07 |
| F07 Drafts | Validator cases; repair then template; state machine; idempotency; suppression; LLM cap | DRF-01..06, LLM-04, LLM-05, REL-03 |
| F08 Export | mailto encoding; CSV; approved-only; domain suppression; no email-sending dependency | EXP-01..04 |
| F09 Agent | Guard; step limit; fallback; identical scores across paths; SSE replay; trace without secrets | AGT-01..06 |
| F10 Demo | Sample with no keys; masking; limits; zero live calls on cached run; partial on cap; monthly guard | DMO-01..05 |
| F11 Packs | Schema validation; no category names in engine; secondary hidden | CAT-01..03 |
| Data | Migrations reset; RLS check query; workspace scoping | DAT-01..03 |
| Security | Secret scan; bundle search; tampered workspace token; rate limits | SEC-01..04 |
| UI | Component tests; Playwright Flow A; forced-error states; Lighthouse | UI-01..05 |

## Named failure scenarios (each has a test)

1. Qloo key missing → kill switch.
2. Qloo 401 mid-run → phase fails, partial data not shown as a ranking.
3. Qloo 429 storm → retries then `qloo_rate_limited`.
4. Qloo returns places outside the city → guard drops and warns.
5. Qloo returns wrong entity type with 200 → guard raises contract violation.
6. Ollama 401 → deterministic plan; template drafts.
7. Gemma returns text instead of tool calls twice → fallback.
8. Website redirects to `169.254.169.254` → blocked.
9. Overpass 429 → backoff, then continue without OSM.
10. Hunter 451 → suppression.
11. Hunter cap reached → "not checked (limit reached)".
12. Draft cites an evidence id from another venue → rejected.
13. User edits an approved draft → status `edited`, export blocked until re-approved.
14. Another workspace requests my run → 404.
15. SSE disconnect mid-run → replay without duplicates.

## RLS check query (DAT-02)

```sql
select c.relname, c.relrowsecurity
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r';
-- every row must show relrowsecurity = true

select * from pg_policies where schemaname = 'public';
-- must return zero rows
```

## Manual test script (before demo recording)

1. Private browser window → landing → "See a sample run" → browse results, venue detail, trace, outreach. Confirm masked emails.
2. Start a live run with the demo brand → watch progress → results in under 90 seconds (warm cache).
3. Select 5 venues → find contacts → generate drafts → edit one → approve three → export CSV and open one mailto.
4. Add a domain to suppression → regenerate drafts → that venue is excluded.
5. Set an invalid Qloo key on the API → start a run → see the kill-switch error. Restore the key.
6. Set `LLM_PROVIDER=fake` → same run → identical ranking; drafts differ.
7. Keyboard-only pass of steps 2–3. Check at 360 px width.
