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
| Database | Supabase Cloud (production project) | `supabase link --project-ref <prod-ref> && supabase db push`, or `uv run python scripts/migrate.py --url <pooler URL>`. The Render build command below also applies new migrations on every deploy |
| API | Render (web service, Python) | Root directory `apps/api` (Render uses uv because `uv.lock` is there). Set `PYTHON_VERSION=3.12.13`: Render defaults to 3.14, reads `.python-version` only at the repo root, and doesn't let uv download Python. Build `uv sync --frozen --no-dev && uv run --no-sync python scripts/migrate.py`. Start `uv run --no-sync uvicorn tasteroute_api.main:app --host 0.0.0.0 --port $PORT`. Health check `/health`. Env: `APP_ENV=production`, a generated `SESSION_SECRET`, `DATABASE_URL` (Supabase transaction pooler, port 6543) with `DB_STATEMENT_CACHE_SIZE=0`, `CORS_ORIGINS` (the web origin), `QLOO_API_KEY`, `OLLAMA_API_KEY`, `OSM_USER_AGENT` (with a contact), `SUPABASE_URL`, `SUPABASE_ANON_KEY`, optional `HUNTER_API_KEY`, `DEMO_RUN_ID` after seeding. One instance only (rate limiter and Nominatim/Overpass limiters are in-process) |
| Web | Vercel, root `apps/web` | Set `NEXT_PUBLIC_API_URL` to the API URL, plus `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`; add the web origin to `CORS_ORIGINS` and to Supabase's redirect URLs (`https://<web>/**`) |

After deploy: run `seed_demo.py` against production (or copy the demo rows), set `DEMO_RUN_ID`, open `/sample` in a private window, then run one live run.

### Client IP (SEC-05)

Per-IP limits use the `X-Forwarded-For` entry `TRUSTED_PROXY_HOPS` from the right; anything to its left was sent by the client. Confirm the value once per host:

1. Set `LOG_LEVEL=debug` and redeploy.
2. `curl -s -H "X-Forwarded-For: 1.2.3.4" https://<api>/v1/categories -o /dev/null` (any route works).
3. In the log, find `x-forwarded-for shape: [...]`. `1.2.3.4` hashes to `python3 -c "import hashlib;print(hashlib.sha256(b'1.2.3.4').hexdigest()[:6])"`. `TRUSTED_PROXY_HOPS` = the number of entries to the right of that hash (1 when the host appends only your real IP; 2 when it also appends its own proxy).
4. Set it, set `LOG_LEVEL=info`, redeploy, and remove the debug line in `security.py`.

Other demo limits: `PUBLIC_RUNS_PER_IP_PER_DAY` (3) and `PUBLIC_RUNS_PER_DAY_GLOBAL` (40 live runs by everyone per 24 h; the sample run is never limited). Runs a restart interrupted are closed on the next start (`error_code=interrupted`).

### Uptime (REL-08)

`.github/workflows/uptime.yml` curls `/health`, `/v1/demo` and the web `/sample` every 10 minutes until 2026-11-17; a failure emails the repo owner and the requests keep a free instance awake. It stays off until the repo variables `UPTIME_ENABLED=true`, `API_URL` and `WEB_URL` are set (Settings → Secrets and variables → Actions → Variables).

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
| "The public demo has used today's live runs" | `PUBLIC_RUNS_PER_DAY_GLOBAL` reached (all visitors, rolling 24 h) | Wait, or raise it; the sample run still works |
| "Live runs are limited to N per day" | `PUBLIC_RUNS_PER_IP_PER_DAY` reached (rolling 24 h, per IP or workspace) | Wait, or raise it in `apps/api/.env` and restart the API; `0` = no limit (local only) |
| Hunter 429 or credits out | Limits | Back off; use cached demo; upgrade one month if needed |
| Browser shows CORS error | Web origin missing | Add it to `CORS_ORIGINS` |
| Sample page empty | `DEMO_RUN_ID` unset or wrong database | Seed and set the id |
