"""Phase 0 spike S5: prove native tool calling on Ollama Cloud with the configured model.

Runs N two-tool round trips (model calls a tool, we return a result, model calls finish).
Usage: uv run python scripts/spike_llm_tools.py [--runs 5] [--out ../../docs/llm-sample.json]
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rank_venues",
            "description": "Rank venues in the run's city by taste fit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "venue_types": {"type": "array", "items": {"type": "string"}},
                    "max_venues": {"type": "integer", "minimum": 10, "maximum": 60},
                },
                "required": ["venue_types"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_phase",
            "description": "End the phase with a one-paragraph summary.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


def env(name: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{name} missing")


async def one(client: httpx.AsyncClient, model: str) -> dict:
    messages: list[dict] = [
        {
            "role": "system",
            "content": "You are a planner. Call exactly ONE tool per turn and wait for its result. "
            "First call rank_venues with venue_types ['cafe','bar']; after you see its result, call finish_phase.",
        },
        {"role": "user", "content": "Start the scout phase for Brooklyn."},
    ]
    t = time.perf_counter()
    body = {"model": model, "messages": messages, "tools": TOOLS, "stream": False, "options": {"temperature": 0.2}}
    r1 = (await client.post("/api/chat", json=body)).json()
    msg = r1["message"]
    calls = msg.get("tool_calls") or []
    first = calls[0]["function"] if calls else None
    messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": calls})
    for c in calls:
        result = {"ranked": 42, "top": ["SEY Coffee"]} if c["function"]["name"] == "rank_venues" else {"ok": True}
        messages.append({"role": "tool", "tool_name": c["function"]["name"], "content": json.dumps(result)})
    r2 = (await client.post("/api/chat", json={**body, "messages": messages})).json()
    calls2 = r2["message"].get("tool_calls") or []
    second = calls2[0]["function"] if calls2 else None
    names = [c["function"]["name"] for c in calls] + [c["function"]["name"] for c in calls2]
    ok = names[:1] == ["rank_venues"] and "finish_phase" in names
    return {"ok": ok, "ms": int((time.perf_counter() - t) * 1000), "first": first, "second": second, "raw1": r1, "raw2": r2}


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--out", default=None)
    a = p.parse_args()
    model = env("OLLAMA_MODEL")
    async with httpx.AsyncClient(
        base_url=env("OLLAMA_BASE_URL"), headers={"Authorization": f"Bearer {env('OLLAMA_API_KEY')}"}, timeout=120
    ) as c:
        results = [await one(c, model) for _ in range(a.runs)]
    for i, r in enumerate(results, 1):
        print(i, "ok" if r["ok"] else "FAIL", f"{r['ms']}ms", r["first"], "->", (r["second"] or {}).get("name"))
    print(f"{sum(r['ok'] for r in results)}/{len(results)} round trips succeeded with {model}")
    if a.out:
        Path(a.out).write_text(json.dumps(results[0], indent=1))


if __name__ == "__main__":
    asyncio.run(main())
