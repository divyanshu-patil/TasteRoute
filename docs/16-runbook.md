# 16. Runbook: setup, run, seed, deploy, troubleshoot

## Prerequisites

- Node.js (version used by the existing Turborepo) and pnpm
- Python 3.12 and `uv`
- Supabase CLI; Docker if you want local Supabase (`supabase start`)
- Accounts and keys: Qloo hackathon API key, Ollama Cloud API key, Hunter API key, Supabase project(s)

## First-time setup

```bash
# 1. Dependencies
pnpm install
cd apps/api && uv sync && cd ../..

# 2. Database: local Postgres 15, or a Supabase project (put its URL in DATABASE_URL)
createdb tasteroute                                        # local only
cd apps/api && uv run python scripts/migrate.py && cd ../..  # applies supabase/migrations/*.sql in order

# 3. Environment
cp apps/api/.env.example apps/api/.env          # fill values (see docs/03-architecture.md)
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > apps/web/.env.local

# 4. Check health
pnpm dev                                         # runs web on :3000 and api on :8000
curl -s localhost:8000/health
```

`apps/api/package.json` scripts (so Turborepo can run the API):

```json
{
  "name": "api",
  "private": true,
  "scripts": {
    "dev": "uv run uvicorn tasteroute_api.main:app --reload --port 8000",
    "lint": "uv run ruff check . && uv run ruff format --check . && uv run mypy src",
    "test": "uv run pytest -m \"not live\"",
    "build": "uv run python scripts/export_openapi.py"
  }
}
```

## Phase 0 scripts

```bash
cd apps/api
uv run python scripts/spike_qloo.py --city "<city>" --brand "<brand>" --out tests/fixtures/qloo/
uv run python scripts/spike_llm_tools.py            # proves Gemma 4 Cloud tool calling
uv run python scripts/record_fixture.py hunter --domain <venue-domain>
uv run python scripts/record_fixture.py overpass --city "<city>" --type cafe
```

## Seeding the demo run

```bash
cd apps/api
uv run python scripts/seed_demo.py [--outreach 8]   # fictional Fieldnote Drinks Co., Brooklyn, cafés and bars; spends live calls
# prints DEMO_RUN_ID and the calls spent. /v1/demo serves the newest demo-workspace run;
# set DEMO_RUN_ID only to pin a specific run (for example in production).
```

## Evaluation

```bash
uv run python scripts/evaluate.py            # setups A, B, C -> docs/evaluation-results.md and docs/evaluation_pairs.csv
uv run python scripts/evaluate.py --score ../../docs/evaluation_pairs.csv   # after the judge fills better_fit
```

## Useful SQL

```sql
-- Live Qloo calls in the last 30 days (budget)
select count(*) from qloo_calls where cache_hit = false and created_at > now() - interval '30 days';

-- Calls per run
select run_id, count(*) filter (where not cache_hit) live, count(*) filter (where cache_hit) cached
from qloo_calls group by run_id order by max(created_at) desc limit 10;

-- RLS check: see docs/13-test-plan.md
```

## Deployment

| Part | Where | Notes |
|---|---|---|
| Database | Supabase Cloud (production project) | `supabase link --project-ref <prod-ref> && supabase db push` |
| API | Render, Railway or Fly.io | Start command `uv run uvicorn tasteroute_api.main:app --host 0.0.0.0 --port $PORT`; set all env vars; one instance (rate limiter and Nominatim/Overpass limiters are in-process) |
| Web | Vercel, root `apps/web` | Set `NEXT_PUBLIC_API_URL` to the API URL; add the web origin to `CORS_ORIGINS` |

After deploy: run `seed_demo.py` against production (or copy the demo rows), set `DEMO_RUN_ID`, open `/sample` in a private window, then run one live run.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `prepared statement ... does not exist` | Transaction pooler with asyncpg statement cache | `statement_cache_size=0`, or use direct/session connection |
| Qloo 401 | Wrong key or header | Check `QLOO_API_KEY`, header `X-Api-Key`, base URL |
| Qloo results ignore the city | Location parameter name or format wrong; silent 200 | Re-check `docs/qloo-contract.md`; guards should warn |
| Ollama 401/404 | Key missing or model name not in `/api/tags` | Fix `OLLAMA_API_KEY`, `OLLAMA_MODEL` |
| Model replies with text, not tool calls | Tool calling unsupported or prompt issue | Planner variant or deterministic fallback runs; check `docs/llm-contract.md` |
| Overpass 429/504 | Public instance overloaded | Wait; use cached results; retry later |
| Nominatim blocked | Missing or generic User-Agent, too many requests | Set `OSM_USER_AGENT` with contact; keep 1 req/s |
| No suggestions while typing | Photon down or throttling | Nothing to fix in the app: Enter still searches through Nominatim. Point `PHOTON_BASE_URL` at another Photon instance if it lasts |
| "Live runs are limited to N per day" | `PUBLIC_RUNS_PER_IP_PER_DAY` reached (rolling 24 h, per IP or workspace) | Wait, or raise it in `apps/api/.env` and restart the API; `0` = no limit (local only) |
| Hunter 429 or credits out | Limits | Back off; use cached demo; upgrade one month if needed |
| Browser shows CORS error | Web origin missing | Add it to `CORS_ORIGINS` |
| Sample page empty | `DEMO_RUN_ID` unset or wrong database | Seed and set the id |
