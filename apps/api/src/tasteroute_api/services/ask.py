"""Questions about a run's results, answered by the LLM from the stored results only (no Qloo or web calls)."""

import json
from collections.abc import AsyncIterator
from typing import Any

from ..agent.context import Services
from ..errors import LLMUnavailable
from ..llm.prompts import load
from ..schemas import AskIn, RouteOut, VenueRow


def context(run: dict[str, Any], rows: list[VenueRow], route: RouteOut | None) -> str:
    """The run as plain text: the only data the answer may use."""
    lift = "taste percentile minus mass-market taste percentile"
    lines = [
        f"Brand: {run['brand']}", f"City: {run['city']}", f"Products: {', '.join(run['products'])}",
        f"Qloo taste signal (brands matched): {', '.join(run['signal']) or 'none'}",
        f"Venues ranked: {len(rows)}. Columns: rank | name | type | neighbourhood | fit 0-100 | lift ({lift}, points) | "
        "confidence | best product | contact status | LLM rank | reason",
    ]
    lines += [
        f"#{v.rank} | {v.name} | {v.venue_type} | {v.neighborhood or '-'} | {round(v.fit * 100)} | {round(v.lift * 100):+d} | "
        f"{v.confidence} | {v.best_product.name if v.best_product else '-'} | {v.contact_status} | {v.llm_rank or '-'} | "
        f"{(v.reason or '-')[:240]}"
        for v in rows
    ]
    if route:
        lines.append("Taste route (walkable areas, strongest hotspot first):")
        lines += [f"- {a.name}: hotspot {a.lift:+}, {', '.join(f'#{x.rank} {x.name}' for x in a.stops)}" for a in route.areas]
    return "\n".join(lines)


async def ask(s: Services, data: str, body: AskIn) -> AsyncIterator[str]:
    """NDJSON lines: {"delta": text} as the answer is written, then {"error": message} if it stops early."""
    system, version = load("ask_run")
    messages: list[dict[str, Any]] = [{"role": "system", "content": f"{system}\n\nRun data:\n{data}"}]
    messages += [{"role": t.role, "content": t.content} for t in body.history[-6:]]
    messages.append({"role": "user", "content": body.question})
    wrote = False
    try:
        # ponytail: not tied to run_id, so chat never eats the run's LLM cap; the per-IP rate limit bounds spend
        async for chunk in s.llm.stream(messages, purpose="ask", prompt_version=version, temperature=0.0, max_tokens=500):
            wrote = wrote or bool(chunk.strip())
            yield json.dumps({"delta": chunk}) + "\n"
        if not wrote:
            yield json.dumps({"delta": "That isn't in this run's results."}) + "\n"
    except LLMUnavailable:
        yield json.dumps({"error": "The AI is unavailable right now. Please try again in a minute."}) + "\n"
