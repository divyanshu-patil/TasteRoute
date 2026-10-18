# F09. Agent orchestration, live progress and trace

## Purpose

Run the work as an **agent** (required by the hackathon rules) that chooses and calls tools, while guaranteeing the same correct result every time, and show the user and judges exactly what happened.

## How it works

1. **Phases.** `scout` (resolve, rank, fit, evidence) starts automatically. `outreach` (contacts, drafts) starts when the user selects venues.
2. **Agent loop** (`agent/loop.py`), per phase:
   - System prompt describes the goal, the tools, the order rules, and limits.
   - The model replies with native tool calls (Ollama `/api/chat` with `tools`). Each call is checked by the **plan guard** before running.
   - Tool results are summarised into compact JSON (ids and counts, not raw payloads) and returned as `role: "tool"` messages with `tool_name`.
   - The loop ends when the model calls `finish_phase`, or after `LLM_MAX_STEPS_PER_PHASE` steps.
3. **Plan guard** (`agent/plan_guard.py`):
   - Allowed tools per phase. Scout: `resolve_entities`, `rank_venues`, `match_products`, `attach_evidence`, `finish_phase`. Outreach: `find_contacts`, `draft_pitches`, `finish_phase`.
   - Required order: `resolve_entities` before `rank_venues`; `rank_venues` before `match_products` and `attach_evidence`; `find_contacts` before `draft_pitches`.
   - Arguments validated with Pydantic; ids must exist in this run.
   - Repeated identical calls are refused.
   - A refused call returns an error message to the model, counted as a step.
4. **Deterministic fallback.** If the model makes two consecutive invalid calls, times out, or the provider does not support tool calling, the run switches to `agent/deterministic_plan.py`, which calls the same tools in the required order. The run records `orchestration: "agent"` or `"deterministic_fallback"` and the reason.
5. **Same answer either way.** Tools are deterministic over Qloo responses, so the ranking does not depend on which path ran.
6. **Events** are written to `run_events` and streamed over SSE: `phase_started`, `tool_call` (name, arguments summary), `qloo_call` (call id, endpoint, cache_hit, duration), `external_call`, `step_done`, `warning`, `phase_done`, `failed`.
7. **Trace page** lists every LLM step, tool call, Qloo call and external call in order, with filters. API keys and full prompts are never shown.

## Tools (summary; full schemas in `05-agent-and-llm.md`)

| Tool | Phase | Does |
|---|---|---|
| `resolve_entities` | scout | F02 for all products |
| `rank_venues` | scout | F03 for chosen venue types |
| `match_products` | scout | F04 |
| `attach_evidence` | scout | F05 for the top N |
| `find_contacts` | outreach | F06 for selected venues |
| `draft_pitches` | outreach | F07 for venues with contacts |
| `finish_phase` | both | Ends the phase with a short summary |

Intake (F01) runs before the agent as a single LLM call, not a tool loop.

## Failure handling

| Failure | Behaviour |
|---|---|
| Model returns text instead of tool calls | Count as invalid; after 2, deterministic fallback |
| Ollama 401 | Run continues with the deterministic plan; drafts use the template; banner explains the LLM is unavailable |
| Tool raises a Qloo error | Phase fails with that error (fail closed) |
| SSE disconnect | Client reconnects with `Last-Event-ID`; server replays missing events from `run_events` |

## Tests

| What | How |
|---|---|
| Guard refuses out-of-order and unknown tools and bad ids | Unit tests |
| Fallback after two invalid calls | Unit test with `FakeProvider` scripted to misbehave |
| Agent path and deterministic path give identical venue scores | Integration test |
| SSE replay from `Last-Event-ID` | API test |
| Trace includes every Qloo call and never a key | API test plus string search |
| Step limit respected | Unit test |

Acceptance: AGT-01 to AGT-06, LLM-03.
