"""Agent loop on native tool calling, with the deterministic plan as a safety net (F09)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from ..errors import LLMUnavailable
from ..llm.prompts import load
from ..services import contacts, drafts
from . import tools
from .context import RunContext
from .plan_guard import PlanGuard

Tool = Callable[..., Awaitable[dict[str, Any]]]
TOOLS: dict[str, Tool] = {
    "resolve_entities": tools.resolve_entities,
    "rank_venues": tools.rank_venues,
    "match_products": tools.match_products,
    "attach_evidence": tools.attach_evidence,
    "find_contacts": contacts.find_contacts,
    "draft_pitches": drafts.draft_pitches,
    "finish_phase": tools.finish_phase,
}
DESCRIPTIONS = {
    "resolve_entities": "Resolve the run's products to Qloo entities. Suggests comparable brands for unknown products.",
    "rank_venues": "Rank venues in the run's city by taste fit with lift over a popularity baseline.",
    "match_products": "Find the best product for each ranked venue.",
    "attach_evidence": "Attach Qloo explanations and evidence to the top venues.",
    "find_contacts": "Find public business contacts for selected venues.",
    "draft_pitches": "Write grounded pitch drafts for venues that have contacts.",
    "finish_phase": "End the current phase with a one-paragraph summary for the user.",
}
PARAMS: dict[str, dict[str, Any]] = {
    "resolve_entities": {"product_ids": {"type": "array", "items": {"type": "string"}}},
    "rank_venues": {"venue_types": {"type": "array", "items": {"type": "string"}},
                    "max_venues": {"type": "integer", "minimum": 10, "maximum": 60}},
    "match_products": {},
    "attach_evidence": {"top_n": {"type": "integer", "minimum": 5, "maximum": 40}},
    "find_contacts": {"venue_ids": {"type": "array", "items": {"type": "string"}}},
    "draft_pitches": {"venue_ids": {"type": "array", "items": {"type": "string"}}},
    "finish_phase": {"summary": {"type": "string", "maxLength": 500}},
}
REQUIRED = {"resolve_entities": ["product_ids"], "rank_venues": ["venue_types"], "attach_evidence": ["top_n"],
            "find_contacts": ["venue_ids"], "draft_pitches": ["venue_ids"], "finish_phase": ["summary"]}


def schemas(names: list[str]) -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {
            "name": n, "description": DESCRIPTIONS[n],
            "parameters": {"type": "object", "properties": PARAMS[n], "required": REQUIRED.get(n, [])}}}
        for n in names
    ]


def _summarise_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: (f"{len(v)} ids" if isinstance(v, list) and len(v) > 4 else v) for k, v in args.items()}


async def execute(ctx: RunContext, guard: PlanGuard, name: str, args: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    await ctx.emit("tool_call", {"step": len(guard.done) + 1, "tool": name, "args_summary": _summarise_args(args)})
    call_args = {**defaults.get(name, {}), **{k: v for k, v in args.items() if v is not None}}
    result = await TOOLS[name](ctx, **call_args)
    guard.record(name, args)
    if name == "find_contacts":
        guard.expected["draft_venue_ids"] = set(result.get("venue_ids_with_contact", []))
        defaults["draft_pitches"] = {"venue_ids": sorted(guard.expected["draft_venue_ids"])}
    await ctx.emit("step_done", {"step": len(guard.done), "tool": name, "summary": result})
    return result


async def run_phase(ctx: RunContext, phase: str, selected_venue_ids: list[str] | None = None) -> tuple[str, str | None, str]:
    """Returns (orchestration, reason, summary). Qloo errors propagate: the phase fails closed."""
    s = ctx.svc.settings
    guard = PlanGuard(phase, {
        "product_ids": set(ctx.products), "venue_types": set(ctx.venue_types), "venue_ids": set(selected_venue_ids or []),
    })
    defaults: dict[str, dict[str, Any]] = {"find_contacts": {"venue_ids": selected_venue_ids or []}}
    prompt, version = load("agent_scout" if phase == "scout" else "agent_outreach")
    state = {
        "brand": ctx.brand["name"],
        "products": [{"product_id": pid, "name": p["name"]} for pid, p in ctx.products.items()],
        "city": ctx.city.get("name"),
        "venue_types": ctx.venue_types,
    }
    if phase == "outreach":
        state["selected_venue_ids"] = selected_venue_ids or []
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Run state:\n" + json.dumps(state)},
    ]
    names = [n for n in TOOLS if n in guard.remaining() + ["finish_phase"]]
    invalid_streak, reason, summary = 0, None, ""
    if not ctx.svc.llm.provider.supports_tools:
        reason = "provider does not support tool calling"
    for _ in range(s.llm_max_steps_per_phase if reason is None else 0):
        try:
            r = await ctx.svc.llm.chat(messages, tools=schemas(names), purpose="agent_step", prompt_version=version,
                                       run_id=ctx.run_id, temperature=s.llm_temperature_tools, max_tokens=400)
        except LLMUnavailable as e:
            reason = f"LLM unavailable: {e.detail}"
            break
        if not r.tool_calls:
            invalid_streak += 1
            messages += [{"role": "assistant", "content": r.content[:2000]},
                         {"role": "user", "content": "Reply with exactly one tool call."}]
            if invalid_streak >= 2:
                reason = "model replied with text instead of tool calls twice"
                break
            continue
        messages.append({"role": "assistant", "content": r.content or "",
                         "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}} for c in r.tool_calls]})
        any_valid = False
        for call in r.tool_calls:
            args, err = guard.check(call.name, call.arguments)
            if err or args is None:
                messages.append({"role": "tool", "tool_name": call.name, "content": json.dumps({"error": err})})
                await ctx.emit("warning", {"code": "guard_refused", "message": f"Plan guard refused {call.name}: {err}"})
                continue
            any_valid = True
            result = await execute(ctx, guard, call.name, args, defaults)
            messages.append({"role": "tool", "tool_name": call.name, "content": json.dumps(result, default=str)[:4000]})
            if call.name == "finish_phase":
                return "agent", None, str(args.get("summary", ""))
        invalid_streak = 0 if any_valid else invalid_streak + 1
        if invalid_streak >= 2:
            reason = "two consecutive invalid tool calls"
            break
    else:
        if reason is None:
            reason = f"step limit of {s.llm_max_steps_per_phase} reached"
    # Deterministic fallback: same tools, required order, skipping what already ran (AGT-03).
    ran = 0
    for name in guard.remaining():
        if name == "draft_pitches" and not guard.expected.get("draft_venue_ids"):
            continue
        args = {"venue_ids": sorted(guard.expected["draft_venue_ids"])} if name == "draft_pitches" else {}
        await execute(ctx, guard, name, args, defaults)
        ran += 1
    if ran == 0:
        return "agent", reason, summary or "Completed by the agent."
    return "deterministic_fallback", reason, summary or "Completed with the deterministic plan."
