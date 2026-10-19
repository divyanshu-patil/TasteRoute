# 07. API specification (FastAPI)

Base path `/v1`. JSON. `snake_case`. Errors are problem objects `{type, title, status, detail, code}`. Pydantic models in `schemas.py` are the source of truth. `scripts/export_openapi.py` writes `apps/api/openapi.json`; `packages/contracts` is generated from it with `openapi-typescript`.

Every request carries the signed workspace token in the `X-Workspace-Token` header (issued by `POST /v1/workspaces/session`; the SSE endpoint takes it as the `token` query parameter). Every query is scoped to that workspace, except the demo run. A missing or invalid token returns 401 `invalid_workspace`.

## Endpoints

| Method and path | Purpose | Feature |
|---|---|---|
| `GET /health` | `{status, db, qloo: ok/unconfigured/error, llm: {provider, model, tools_ok}, hunter: ok/unconfigured, version}` | — |
| `POST /v1/workspaces/session` | Create an anonymous workspace, or validate an existing token → `{workspace_token}` | — |
| `POST /v1/workspaces/login` | `{access_token, workspace_token?}` (Supabase Auth) → `{workspace_token, workspace_id, email}`: the account's workspace, with this browser's work merged in. `400 signin_failed`, `503 auth_unconfigured` | F12 |
| `GET /v1/categories` | Enabled category packs and their venue types | F11 |
| `POST /v1/brands/intake` | `{website_url?, description?}` → proposed profile (not saved yet) | F01 |
| `POST /v1/brands` | Save a confirmed profile and products → `{brand_id, product_ids}` | F01 |
| `GET /v1/brands/{id}` / `PATCH /v1/brands/{id}` | Read or edit a brand and products | F01 |
| `POST /v1/brands/{id}/resolve` | Resolve products to Qloo entities (preview before a run) → per product: entities, dropped names | F02 |
| `GET /v1/qloo/search?q=&type=` | Manual entity search for adding comparables (cached, counts to budget) | F02 |
| `GET /v1/cities/search?q=` | City lookup via Nominatim (cached, 1 req/s); each hit has a plain-English `label` and `detail` | F03 |
| `GET /v1/places/search?q=&bbox=s,w,n,e` | The brand's own location: Nominatim search bounded to the city's box → `[{label, detail, lat, lon}]` | F03 |
| `GET /v1/places/suggest?q=&kind=place\|city&bbox=` | Suggestions while typing, from Photon → `[{label, detail, lat, lon}]`; `[]` when Photon is down. A picked city suggestion is then looked up once with `/v1/cities/search` for its area | F03 |
| `GET /v1/places/reverse?lat=&lon=` | A dropped map pin → nearest address as `{label, detail, lat, lon}` ("Dropped pin" if Nominatim has none) | F03 |
| `POST /v1/runs` | `{brand_id, product_ids, entity_ids_by_product, city_id_or_query, venue_types, base?}`; `base` is the brand's location, used only for distances, never for ranking → `202 {run_id}` | F09 |
| `GET /v1/runs/{id}` | Run status, counters, orchestration, warnings | F09 |
| `GET /v1/runs/{id}/events?token=` | SSE stream; supports `Last-Event-ID` | F09 |
| `GET /v1/runs/{id}/venues?type=&confidence=&product_id=&limit=&offset=` | Ranked venues with fit, lift, confidence, best product, reason | F03–F05 |
| `GET /v1/runs/{id}/venues/{venue_id}` | Venue detail, per-product fit, evidence | F04, F05 |
| `POST /v1/runs/{id}/contacts` | `{venue_ids}` → starts outreach `find_contacts` → `202` | F06 |
| `POST /v1/runs/{id}/cancel` | Stops a running outreach mid-way (its LLM and web calls too); contacts and drafts found so far are kept. Also frees a run left running by an API restart. A no-op otherwise → `202` | F06 |
| `GET /v1/runs/{id}/contacts` | Contact status per selected venue, with the sources checked and the venue's website | F06 |
| `POST /v1/runs/{id}/drafts` | `{venue_ids}` → `draft_pitches` → `202` | F07 |
| `GET /v1/runs/{id}/drafts` | Drafts with status | F07 |
| `PATCH /v1/drafts/{id}` | `{subject?, body?, status?: "approved"}`; edit-after-approve resets to `edited` | F07 |
| `POST /v1/drafts/{id}/regenerate` | Only if not approved or sent | F07 |
| `POST /v1/drafts/{id}/send` | `{google_access_token}` → the sent draft. Sends from the signed-in user's Gmail, once. `403 signin_required`, `403 gmail_reconnect`, `409` already sent or suppressed, `502 gmail_failed` | F12 |
| `GET /v1/runs/{id}/export.csv` | CSV of the run (approved drafts only) | F08 |
| `GET /v1/suppressions` / `POST` / `DELETE /v1/suppressions/{id}` | Manage do-not-contact list | F08 |
| `GET /v1/runs/{id}/trace?kind=qloo|external|llm|tool` | Ordered trace, no secrets | F09 |
| `GET /v1/demo` | Demo run summary (no keys needed) | F10 |
| `POST /v1/runs/{id}/rescore` | Recompute scores with new weights from stored responses (no new calls) | F03 |

## SSE events

| event | data |
|---|---|
| `phase_started` | `{phase, orchestration}` |
| `tool_call` | `{step, tool, args_summary}` |
| `qloo_call` | `{call_id, endpoint, cache_hit, duration_ms, status}` |
| `external_call` | `{call_id, service, cache_hit, status}` |
| `venue` | `{tool, venue, state: checking or done, result, done, of}`: outreach progress per venue (contacts, then drafts) |
| `step_done` | `{step, tool, summary}` |
| `warning` | `{code, message}` |
| `phase_done` | `{phase, summary}` |
| `failed` | `{code, message}` |

## Key response model: venue row

```json
{
  "venue_id": "uuid",
  "rank": 1,
  "name": "string",
  "venue_type": "cafe",
  "fit": 0.87,
  "lift": 0.24,
  "confidence": "high",
  "flags": ["not_in_baseline"],
  "best_product": {"product_id": "uuid", "name": "string", "label": "clear"},
  "reason": "Guests here over-index on specialty coffee and natural wine (Qloo). Product B fits best (our inference).",
  "evidence_count": 4,
  "contact_status": "not_checked"
}
```

## Validation

- `website_url`: http/https, public host only (SSRF guard), ≤ 2,048 chars.
- `description`: ≤ 1,500 chars. Products: 1–5. Venue types: 1–6 from the enabled pack. Outreach venue ids: ≤ `MAX_OUTREACH_VENUES_PER_RUN`, must belong to the run.
- Unknown fields rejected.

## Error codes

`invalid_workspace`, `url_not_allowed`, `website_unreadable`, `unsupported_business`, `no_entities_resolved`, `qloo_unconfigured`, `qloo_auth`, `qloo_unavailable`, `qloo_rate_limited`, `qloo_budget_exceeded`, `qloo_contract_violation`, `no_venues`, `hunter_unconfigured`, `hunter_limit_reached`, `llm_unavailable` (non-fatal), `rate_limited`, `validation_error`, `not_found`, `forbidden_workspace`, `draft_locked`, `signin_failed`, `auth_unconfigured`, `signin_required`, `gmail_reconnect`, `gmail_failed`.

## Rate limits

- `POST /v1/runs`: `PUBLIC_RUNS_PER_IP_PER_DAY` per IP and per workspace in a rolling 24 hours (default 3; `0` turns the limit off for local use).
- `POST /v1/brands/intake`: 20 per hour per IP.
- `POST /v1/workspaces/login`: 20 per hour per IP.
- `GET /v1/qloo/search`, `/v1/cities/search`, `/v1/places/search` and `/v1/places/reverse`: 30 per minute per IP. `/v1/places/suggest`: 60 per minute per IP.
