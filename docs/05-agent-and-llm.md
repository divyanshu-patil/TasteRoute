# 05. Agent and LLM

## Model and provider

- **Provider:** Ollama Cloud, called directly over HTTPS with an API key. No local Ollama.
- **Model:** Gemma 4 31B. The Ollama library lists `gemma4:31b` and a cloud tag `gemma4:31b-cloud`, with native function calling, a 256K context, text and image input, and configurable thinking. Ollama's docs say API requests use the names listed at `https://ollama.com/api/tags` (the `-cloud` suffix is for the CLI). **Phase 0 confirms the exact name** and sets `OLLAMA_MODEL`.
- **Endpoint:** `POST {OLLAMA_BASE_URL}/api/chat` with header `Authorization: Bearer {OLLAMA_API_KEY}`, body `{model, messages, tools?, stream, options: {temperature, num_predict}}`.
- **Tool calling:** pass `tools` as `[{type: "function", function: {name, description, parameters (JSON Schema)}}]`. The reply's `message.tool_calls[].function` has `name` and `arguments` (an object). Send results back as `{"role": "tool", "tool_name": "<name>", "content": "<string>"}`. Ollama's tool-calling docs do not state cloud support explicitly, so **Phase 0 must prove tool calling works on Gemma 4 Cloud.** If it does not, the deterministic plan runs and the agent requirement is met through the planner variant below.
- **Structured outputs:** Ollama's docs state cloud models do not support the `format` JSON-schema option. Use prompt-and-validate (below).
- **Sampling:** Gemma's recommended defaults are temperature 1.0, top_p 0.95, top_k 64. For tool choice and JSON use `LLM_TEMPERATURE_TOOLS=0.2`; for email writing `LLM_TEMPERATURE_WRITING=0.7`. Tune in Phase 2.
- **Thinking:** do not include earlier turns' thinking content in the message history; keep only final content and tool calls.

## Where the LLM is used

| Use | Mode | Can it change rankings? |
|---|---|---|
| Brand profile from website text (F01) | One structured call | No |
| Comparable brand **names** (F02) | One structured call per unresolved product | No (Qloo resolves or drops them) |
| Agent tool selection (F09) | Tool-calling loop | No (tools are deterministic, guard enforces order) |
| Pitch emails (F07) | One structured call per venue, validated | No |
| Finding a published email (F06) | One structured call per venue where no pattern found one; the model quotes the page and code checks the quote | No |

The LLM never writes reasons (F05 uses templates), scores or venue lists, and never makes up contacts: it may only point at an address written on the venue's own pages, and code checks that.

## Agent tools (JSON Schemas, simplified)

```json
[
  {"type":"function","function":{"name":"resolve_entities","description":"Resolve the run's products to Qloo entities. Suggests comparable brands for unknown products.","parameters":{"type":"object","properties":{"product_ids":{"type":"array","items":{"type":"string"}}},"required":["product_ids"]}}},
  {"type":"function","function":{"name":"rank_venues","description":"Rank venues in the run's city by taste fit with lift over a popularity baseline.","parameters":{"type":"object","properties":{"venue_types":{"type":"array","items":{"type":"string"}},"max_venues":{"type":"integer","minimum":10,"maximum":60}},"required":["venue_types"]}}},
  {"type":"function","function":{"name":"match_products","description":"Find the best product for each ranked venue.","parameters":{"type":"object","properties":{},"required":[]}}},
  {"type":"function","function":{"name":"attach_evidence","description":"Attach Qloo explanations and evidence to the top venues.","parameters":{"type":"object","properties":{"top_n":{"type":"integer","minimum":5,"maximum":40}},"required":["top_n"]}}},
  {"type":"function","function":{"name":"find_contacts","description":"Find public business contacts for selected venues.","parameters":{"type":"object","properties":{"venue_ids":{"type":"array","items":{"type":"string"}}},"required":["venue_ids"]}}},
  {"type":"function","function":{"name":"draft_pitches","description":"Write grounded pitch drafts for venues that have contacts.","parameters":{"type":"object","properties":{"venue_ids":{"type":"array","items":{"type":"string"}}},"required":["venue_ids"]}}},
  {"type":"function","function":{"name":"finish_phase","description":"End the current phase with a one-paragraph summary for the user.","parameters":{"type":"object","properties":{"summary":{"type":"string","maxLength":500}},"required":["summary"]}}}
]
```

Tool results returned to the model are compact: counts, ids, top-5 names, warnings. Never raw Qloo payloads.

## System prompt for the scout phase (`prompts/agent_scout.md`, outline)

- Role: "You are TasteRoute's planner. Your job is to rank venues for the user's products using the tools. You never invent venues, scores or facts."
- Goal and current state (products, city, venue types, what has been done).
- Rules: call `resolve_entities` first; then `rank_venues` with the run's venue types; then `match_products`; then `attach_evidence` with `top_n` 30; then `finish_phase`. If a tool returns an error, decide whether to retry once or finish with an explanation.
- Output: tool calls only, except the final summary.

The outreach prompt is similar with its own tools and rules.

## Planner variant (if native tool calling fails on Gemma 4 Cloud)

The model returns one JSON object per step: `{"tool": "<name>", "arguments": {...}}`, validated with Pydantic and the plan guard, executed, and fed back as a user message. This keeps the run agentic without native tool calls. If that also fails twice, the deterministic plan runs.

## Structured output helper (`llm/structured.py`)

1. Each task has a Pydantic model and a prompt that includes the JSON Schema as text and says "Return only one JSON object."
2. Extract JSON from the reply (strip code fences, take the outermost object).
3. Validate. On failure, one repair call with the invalid output and the validation errors.
4. Still invalid: raise `LLMBadResponseError`; the caller uses its fallback (manual form, template draft, deterministic plan).

## Provider layer

```python
class LLMProvider(Protocol):
    name: str
    supports_tools: bool
    supports_native_schema: bool
    async def chat(self, messages: list[dict], *, tools: list[dict] | None = None,
                   temperature: float, max_tokens: int, timeout: float) -> LLMResult: ...
    async def aclose(self) -> None: ...

@dataclass
class LLMResult:
    content: str
    tool_calls: list[ToolCall]      # normalised {id, name, arguments}
    model: str
    provider: str
    usage: dict[str, int] | None
```

Adapters: `OllamaCloudProvider` (default), `GeminiProvider` (portability; verify its request format against current Google docs before coding), `FakeProvider` (tests; scripted replies including tool calls). Only files in `llm/` may name a provider. Selection by `LLM_PROVIDER`. No gateway services.

## Prompts (`llm/prompts/`)

| File | Used by | Output |
|---|---|---|
| `brand_profile.md` | F01 | Brand profile JSON |
| `suggest_comparables.md` | F02 | `{"names": [string]}` up to 5 |
| `agent_scout.md` | F09 | Tool calls, then summary |
| `agent_outreach.md` | F09 | Tool calls, then summary |
| `pitch_email.md` | F07 | Subject, body, cited evidence ids |
| `repair_json.md` | structured helper | Corrected JSON |

Each prompt has a version string stored with its outputs.

## Limits

- `LLM_MAX_STEPS_PER_PHASE` (default 12).
- LLM calls per run: intake 1–2, comparables up to 5, agent steps up to 24, drafts up to 25 plus 25 repairs. Hard cap 80 per run.
- Timeouts `LLM_TIMEOUT_SECONDS`; one retry on 5xx or timeout.

## Security

- Keys only in the API environment; never logged.
- Website text is untrusted input. The brand-profile prompt wraps it in clear delimiters and instructs the model to treat it as data. Tool calls are guarded, so injected text cannot trigger contact lookups or drafts on its own.
- Full prompts and completions are logged only at debug level, which is off in production.

## Tests

- Unit: structured extraction, repair, guard, planner variant parsing.
- Integration: `FakeProvider` scripts for normal runs, invalid calls, text-only replies, timeouts.
- Live (manual): `scripts/spike_llm_tools.py` proves tool calling on the configured model and records a sample exchange in `docs/llm-contract.md`.
