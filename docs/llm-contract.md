# LLM contract (verified live, Phase 0, 2026-10-19)

| Fact | Verified value |
|---|---|
| Endpoint | `POST https://ollama.com/api/chat` |
| Auth | `Authorization: Bearer <OLLAMA_API_KEY>` |
| Model name | **`gemma4:31b`** (from `GET https://ollama.com/api/tags`, 22 models listed; no `-cloud` suffix in the API) |
| Tool calling | Native, via `tools: [{type: "function", function: {name, description, parameters}}]` |
| Reply | `message.tool_calls[] = {id, function: {index, name, arguments: {...object}}}`, `message.content` empty |
| Tool result message | `{"role": "tool", "tool_name": "<name>", "content": "<json string>"}` |
| Latency | 2.1–3.8 s per two-turn round trip |
| Usage fields | `prompt_eval_count`, `eval_count`, `total_duration` |

## Behaviour that matters

1. **Parallel calls.** With a prompt that lists the whole plan, Gemma returns several tool calls in one turn (e.g. `rank_venues` and `finish_phase` together, before seeing any result). The agent loop therefore executes calls in order and runs each through the plan guard; a premature `finish_phase` is refused.
2. **"One tool per turn" works.** With the instruction "Call exactly ONE tool per turn and wait for its result", the two-tool round trip succeeded **5/5** (`scripts/spike_llm_tools.py --runs 5`). The scout and outreach prompts use this wording.
3. Structured outputs (`format`) are not used: prompt-and-validate JSON (`llm/structured.py`).

## Sample exchange (trimmed, from `tests/fixtures/llm_tool_roundtrip.json`)

```json
{"message": {"role": "assistant", "content": "",
  "tool_calls": [{"id": "call_…", "function": {"index": 0, "name": "rank_venues",
                  "arguments": {"venue_types": ["cafe", "bar"]}}}]}}
```
then, after `{"role":"tool","tool_name":"rank_venues","content":"{\"ranked\": 42, \"top\": [\"SEY Coffee\"]}"}`:
```json
{"message": {"role": "assistant", "content": "",
  "tool_calls": [{"function": {"name": "finish_phase", "arguments": {"summary": "…"}}}]}}
```
