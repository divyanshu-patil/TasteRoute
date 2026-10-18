# 12. Acceptance criteria

Each criterion has an ID, a measurable statement, how it is checked, and a priority (**MVP** must pass before submission; **Stretch** only if time allows). Record results in `docs/progress.md` with the date and the test or evidence.

## Intake (F01)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| INT-01 | Given a public website, the app reads at most 3 same-domain pages and at most 12,000 characters of text | Unit + API test with fixtures | MVP |
| INT-02 | The proposed profile validates against the schema, or the user gets an empty editable form | Unit tests with fake LLM | MVP |
| INT-03 | Unreadable sites lead to the description path, not an error page | API test | MVP |
| INT-04 | A business whose prospects are not consumer-facing sees the unsupported explanation and cannot start a run unless they confirm an override, which is logged | API test | MVP |
| INT-05 | User edits to profile and products persist and are used by the run | API test | MVP |

## Entities (F02)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| ENT-01 | Each product ends as resolved (with entities) or unresolved (with a message) | API test | MVP |
| ENT-02 | Entity ids stored only come from Qloo responses; LLM suggestions are names only | Unit test | MVP |
| ENT-03 | Name matching accepts known variants and rejects unrelated names at threshold 0.85 | Unit tests | MVP |
| ENT-04 | Users can remove an entity and add one found through Qloo search | API test | MVP |
| ENT-05 | A run cannot start without at least one resolved entity | API test | MVP |

## Ranking (F03)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| RNK-01 | For each venue type, one target and one baseline Qloo query are made (or served from cache) | Trace inspection test | MVP |
| RNK-02 | Lift and fit follow the documented formulas; ranking order can differ from raw target order | Unit test with crafted fixture | MVP |
| RNK-03 | Entities outside the radius or of the wrong type are dropped and counted in a warning | Contract test | MVP |
| RNK-04 | Every venue has a confidence label from documented thresholds, explained in the UI | Unit test + UI check | MVP |
| RNK-05 | Fewer than 15 venues or low baseline overlap triggers a coverage notice | Unit test | MVP |
| RNK-06 | At most `MAX_VENUES_PER_RUN` venues are stored per run | Unit test | MVP |

## Product fit (F04)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| FIT-01 | Each venue has a percentile for every scored product | API test | MVP |
| FIT-02 | Best product and label (clear, close, tie, single_product) follow the documented margins | Unit tests | MVP |
| FIT-03 | A failed product query marks only that product unscored | Integration test | MVP |

## Evidence (F05)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| EVD-01 | 100% of displayed venues have a reason and at least one Qloo evidence item | API test | MVP |
| EVD-02 | Every evidence item links to an existing trace row | Integration test | MVP |
| EVD-03 | Inferences are labelled as inferences in API and UI | Unit test + UI check | MVP |

## Contacts (F06)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| CON-01 | OSM `email`/`contact:email` and website tags are used when matched by name and distance | Unit tests | MVP |
| CON-02 | Hunter is called only with venue domains, never social or marketplace domains | Unit test | MVP |
| CON-03 | Contact choice order follows F06; invalid and disposable emails are never used | Unit tests | MVP |
| CON-04 | Hunter 451 adds the address to suppression and stores nothing else | Integration test | MVP |
| CON-05 | No email address is ever constructed; every stored email has a source | Unit test | MVP |
| CON-06 | Hunter calls per run never exceed `HUNTER_MAX_CALLS_PER_RUN` | Integration test | MVP |
| CON-07 | Suppressed emails and domains are skipped in lookups, drafts and export | Integration tests | MVP |

## Drafts (F07)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| DRF-01 | Drafts are created only for selected venues with a usable contact | API test | MVP |
| DRF-02 | The grounding validator rejects invented names, numbers, unknown evidence ids and missing opt-out | Unit tests | MVP |
| DRF-03 | After one failed repair, a template draft labelled `template` is used | Unit test | MVP |
| DRF-04 | Status transitions follow the state machine; editing an approved draft resets it to `edited` | Unit tests | MVP |
| DRF-05 | Every draft contains the opt-out line | Unit test | MVP |
| DRF-06 | Edits are saved and survive reload | API test | MVP |

## Export and suppression (F08)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| EXP-01 | mailto links exist only for approved drafts and are correctly encoded | Unit + API tests | MVP |
| EXP-02 | CSV has the documented columns, escaping and UTF-8 | Unit test | MVP |
| EXP-03 | Users can add and remove suppression entries (email or domain) | API test | MVP |
| EXP-04 | The app never sends email (no SMTP or email-sending dependency in the codebase) | Dependency and code search check | MVP |

## Agent (F09)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| AGT-01 | The plan guard refuses unknown tools, out-of-order calls, bad ids and repeated identical calls | Unit tests | MVP |
| AGT-02 | Each phase stops within `LLM_MAX_STEPS_PER_PHASE` | Unit test | MVP |
| AGT-03 | After two invalid steps or provider failure, the deterministic plan runs and the run records why | Unit + integration tests | MVP |
| AGT-04 | SSE streams all event types and replays from `Last-Event-ID` | API test | MVP |
| AGT-05 | The trace lists every LLM step, tool call, Qloo call and external call; no secret appears | API test + string search | MVP |
| AGT-06 | Agent, planner and deterministic paths produce identical venue scores for the same inputs and cache | Integration test | MVP |

## Demo and budget (F10)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| DMO-01 | `/sample` works with Qloo, Hunter and Ollama keys unset | API test + manual | MVP |
| DMO-02 | Live runs are limited per IP and workspace per day | API test | MVP |
| DMO-03 | An identical run within the cache TTL makes zero live Qloo calls | Integration test | MVP |
| DMO-04 | Hitting a per-run cap keeps partial results and shows a warning | Integration test | MVP |
| DMO-05 | Demo contact emails are masked in UI responses and CSV | API test | MVP |

## Category packs (F11)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| CAT-01 | Venue types, tags and baselines come only from pack files validated at startup | Unit test + grep test | MVP |
| CAT-02 | Unsupported businesses get Flow D | API test | MVP |
| CAT-03 | The fashion pack appears only when enabled after Phase 0 proves coverage | API test | Stretch |

## Qloo integration (cross-cutting)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| QLO-01 | Every ranking, fit and reason shown is derived from stored Qloo responses | Integration test over a fixture run | MVP |
| QLO-02 | **Kill switch:** with an empty or invalid Qloo key, a new run fails in scout with `qloo_unconfigured`/`qloo_auth`; no ranking, fit, reasons or drafts; no drafting LLM call | API test + manual on camera | MVP |
| QLO-03 | A run uses at least four Qloo capabilities: entity search, tag-based place insights with location, baseline query, per-product insights (plus explainability if available) | Trace inspection | MVP |
| QLO-04 | Silent-failure guards run on every response | Contract tests | MVP |
| QLO-05 | The client never exceeds `QLOO_RPS` | Unit test with fake clock | MVP |
| QLO-06 | Responses are cached by normalised key and reused within TTL | Integration test | MVP |
| QLO-07 | `docs/qloo-contract.md` exists with verified parameters and fixtures for every endpoint used | Review | MVP |

## LLM (cross-cutting)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| LLM-01 | Provider names appear only under `llm/` | Grep test in CI | MVP |
| LLM-02 | Switching `LLM_PROVIDER` changes only text; scores are identical | Integration test | MVP |
| LLM-03 | Ollama Cloud is called at `OLLAMA_BASE_URL` with a Bearer key; no local Ollama is required | Manual run on a machine without Ollama installed | MVP |
| LLM-04 | Invalid JSON triggers exactly one repair, then the documented fallback | Unit tests | MVP |
| LLM-05 | LLM calls per run never exceed 80 | Integration test | MVP |
| LLM-06 | `docs/llm-contract.md` records a real tool-calling exchange with the chosen model | Review | MVP |

## Data (Supabase)

| ID | Criterion | Check | Priority |
|---|---|---|---|
| DAT-01 | Migrations apply cleanly to an empty database (`supabase db reset`) | CI or manual | MVP |
| DAT-02 | RLS is enabled on every table and no policy grants anon access | SQL check query | MVP |
| DAT-03 | Every repository query is scoped by workspace; another workspace's run returns 404 | API tests | MVP |
| DAT-04 | Cleanup script applies the retention rules | Integration test on a test database | Stretch |

## API, security, reliability

| ID | Criterion | Check | Priority |
|---|---|---|---|
| API-01 | Endpoints match `openapi.json`; `packages/contracts` is up to date | CI check | MVP |
| API-02 | Invalid input returns 422 with a problem object | API tests | MVP |
| SEC-01 | No secret in repo, logs, traces, API responses or the web bundle | Secret scan + bundle search | MVP |
| SEC-02 | SSRF guard blocks private and metadata addresses including via redirects | Unit tests | MVP |
| SEC-03 | Rate limits on intake, runs and search endpoints | API tests | MVP |
| SEC-04 | Workspace tokens are HMAC-signed; a tampered or missing token returns 401 `invalid_workspace` | API test | MVP |
| REL-01 | Retries with backoff on 429/5xx/timeouts for Qloo, Hunter, Overpass | Integration tests | MVP |
| REL-02 | Every external call has a timeout | Code review + unit test | MVP |
| REL-03 | Draft generation is idempotent per (run, venue, contact) | Integration test | MVP |

## Frontend

| ID | Criterion | Check | Priority |
|---|---|---|---|
| UI-01 | Screens follow `docs/DESIGN.md` | Visual review against the design file | MVP |
| UI-02 | All states in `08-frontend-spec.md` are implemented and reachable | Manual with forced failures | MVP |
| UI-03 | Every number has a tooltip; every reason has source chips linking to the trace | Manual | MVP |
| UI-04 | Keyboard-only completion of Flow A; Lighthouse accessibility ≥ 90; works at 360 px | Lighthouse + manual | MVP |
| UI-05 | Copy never says "will buy" or "demand"; inferences labelled | Text search | MVP |

## Evaluation, repo and submission

| ID | Criterion | Check | Priority |
|---|---|---|---|
| EVL-01 | Qloo-on vs Qloo-off evaluation run and reported in `docs/evaluation-results.md`, including where Qloo did not help | Review | MVP |
| REP-01 | Public repo with an open-source `LICENSE` file | Review | MVP |
| REP-02 | README with setup, architecture diagram, Qloo call chain, kill switch, limits | Review | MVP |
| REP-03 | Clean clone runs with the documented commands | Clean-machine run | MVP |
| REP-04 | Public demo URL works logged out, including `/sample` | Manual from a private window | MVP |
| REP-05 | Demo video recorded, public, matches the working app | Review | MVP |
