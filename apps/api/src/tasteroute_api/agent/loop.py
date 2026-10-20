"""Agent loop on native tool calling, with the deterministic plan as a safety net (F09)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from ..errors import LLMUnavailable
from ..llm.prompts import load
from ..services import contacts, drafts
from . import rules, tools
from .context import RunContext
from .plan_guard import PHASE_TOOLS, PlanGuard

Tool = Callable[..., Awaitable[dict[str, Any]]]
TOOLS: dict[str, Tool] = {
    "resolve_entities": tools.resolve_entities,
    "suggest_more_comparables": tools.suggest_more_comparables,
    "rank_venues": tools.rank_venues,
    "add_venue_type": tools.add_venue_type,
    "match_products": tools.match_products,
    "attach_evidence": tools.attach_evidence,
    "find_contacts": contacts.find_contacts,
    "draft_pitches": drafts.draft_pitches,
    "finish_phase": tools.finish_phase,
}
DESCRIPTIONS = {
    "resolve_entities": "Resolve the run's products to Qloo entities. Suggests comparable brands for unknown products.",
    "suggest_more_comparables": "Ask for more similar brands for one product; Qloo must confirm each. Give your reason.",
    "rank_venues": "Rank venues in the run's city by taste fit, with lift over mass-market taste at the same venues.",
    "add_venue_type": "Rank one more venue type from the pack (from types_you_can_add). Give your reason.",
    "match_products": "Find the best product for each ranked venue.",
    "attach_evidence": "Attach Qloo explanations and evidence to the top venues.",
    "find_contacts": "Find public business contacts for selected venues.",
    "draft_pitches": "Write grounded pitch drafts for venues that have contacts.",
    "finish_phase": "End the current phase with a one-paragraph summary for the user.",
}
PARAMS: dict[str, dict[str, Any]] = {
    "resolve_entities": {"product_ids": {"type": "array", "items": {"type": "string"}}},
    "suggest_more_comparables": {"product_id": {"type": "string"}, "reason": {"type": "string", "maxLength": 300}},
    "rank_venues": {"venue_types": {"type": "array", "items": {"type": "string"}},
                    "max_venues": {"type": "integer", "minimum": 10, "maximum": 60}},
    "add_venue_type": {"type_id": {"type": "string"}, "reason": {"type": "string", "maxLength": 300}},
    "match_products": {},
    "attach_evidence": {"top_n": {"type": "integer", "minimum": 5, "maximum": 40}},
    "find_contacts": {"venue_ids": {"type": "array", "items": {"type": "string"}}},
    "draft_pitches": {"venue_ids": {"type": "array", "items": {"type": "string"}}},
    "finish_phase": {"summary": {"type": "string", "maxLength": 500}},
}
REQUIRED = {"resolve_entities": ["product_ids"], "suggest_more_comparables": ["product_id", "reason"],
            "rank_venues": ["venue_types"], "add_venue_type": ["type_id", "reason"], "attach_evidence": ["top_n"],
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


DECISIONS = {"suggest_more_comparables", "add_venue_type"}


def _saw(ctx: RunContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """The numbers behind a decision, shown in the trace (F6)."""
    if name == "suggest_more_comparables":
        r = (ctx.settings_json.get("resolution") or {}).get(args["product_id"], {})
        return {"product": ctx.products.get(args["product_id"], {}).get("name"), "similar_brands": r.get("entities"),
                "known_by_name": r.get("known_by_name"), "rounds_so_far": r.get("suggest_rounds"),
                "rule": f"fewer than {rules.MIN_COMPARABLES} similar brands"}
    by_type = ctx.settings_json.get("by_type") or {}
    return {"venues_by_type": by_type, "thin": rules.thin_types(by_type, ctx.venue_types),
            "rule": f"fewer than {rules.MIN_VENUES_PER_TYPE} venues in a type"}


async def execute(ctx: RunContext, guard: PlanGuard, name: str, args: dict[str, Any], defaults: dict[str, Any],
                  by: str = "AI agent") -> dict[str, Any]:
    if name in DECISIONS:
        await ctx.emit("decision", {"tool": name, "by": by, "saw": _saw(ctx, name, args), "reason": args.get("reason", ""),
                                    "args_summary": _summarise_args({k: v for k, v in args.items() if k != "reason"})})
    await ctx.emit("tool_call", {"step": len(guard.done) + 1, "tool": name, "args_summary": _summarise_args(args)})
    ctx.actor = by
    call_args = {**defaults.get(name, {}), **{k: v for k, v in args.items() if v is not None}}
    result = await TOOLS[name](ctx, **call_args)
    guard.record(name, args)
    if name == "find_contacts":
        guard.known["draft_venue_ids"] = set(result.get("venue_ids_with_contact", []))
        defaults["draft_pitches"] = {"venue_ids": sorted(guard.known["draft_venue_ids"])}
    await ctx.emit("step_done", {"step": len(guard.done), "tool": name, "summary": result})
    return result


async def run_phase(ctx: RunContext, phase: str, selected_venue_ids: list[str] | None = None) -> tuple[str, str | None, str]:
    """Returns (orchestration, reason, summary). Qloo errors propagate: the phase fails closed."""
    s = ctx.svc.settings
    guard = PlanGuard(phase, {
        "product_ids": set(ctx.products), "venue_types": set(ctx.venue_types), "venue_ids": set(selected_venue_ids or []),
        "pack_types": {v.id for v in ctx.pack.venue_types},
    })
    defaults: dict[str, dict[str, Any]] = {"find_contacts": {"venue_ids": selected_venue_ids or []}}
    prompt, version = load("agent_scout" if phase == "scout" else "agent_outreach")
    state = {
        "brand": ctx.brand["name"],
        "products": [{"product_id": pid, "name": p["name"]} for pid, p in ctx.products.items()],
        "city": ctx.city.get("name"),
        "venue_types": ctx.venue_types,
        "pack_venue_types": [v.id for v in ctx.pack.venue_types],
    }
    if phase == "outreach":
        state["selected_venue_ids"] = selected_venue_ids or []
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Run state:\n" + json.dumps(state)},
    ]
    names = PHASE_TOOLS[phase]
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
    # Deterministic fallback: the required tools in order, skipping what already ran, and the same decision rules the
    # agent is given, applied at the same points (AGT-03, AGT-09).
    ran = 0
    for name in guard.remaining():
        ran += await _apply_rules(ctx, guard, name, defaults)
        if name == "draft_pitches" and not guard.known.get("draft_venue_ids"):
            continue
        args = {"venue_ids": sorted(guard.known["draft_venue_ids"])} if name == "draft_pitches" else {}
        await execute(ctx, guard, name, args, defaults, by="Fixed plan")
        ran += 1
    if ran == 0:
        return "agent", reason, summary or "Completed by the agent."
    return "deterministic_fallback", reason, summary or "Completed with the deterministic plan."


def _rule_call(ctx: RunContext, before: str) -> tuple[str, dict[str, Any]] | None:
    if before == "rank_venues":
        res = ctx.settings_json.get("resolution") or {}
        pids = rules.needs_comparables(res)
        if not pids:
            return None
        r = res[pids[0]]
        return ("suggest_more_comparables", {"product_id": pids[0], "reason": f"Known through {len(r['entities'])} "
                f"similar brands, fewer than {rules.MIN_COMPARABLES} (round {r['suggest_rounds'] + 1})."})
    if before == "match_products":
        t = rules.type_to_add(ctx.settings_json.get("by_type") or {}, ctx.venue_types, [v.id for v in ctx.pack.venue_types],
                              ctx.settings_json.get("added_types") or [])
        return ("add_venue_type", {"type_id": t, "reason": f"A venue type had fewer than {rules.MIN_VENUES_PER_TYPE} "
                "ranked venues."}) if t else None
    return None


async def _apply_rules(ctx: RunContext, guard: PlanGuard, before: str, defaults: dict[str, Any]) -> int:
    n = 0
    while (call := _rule_call(ctx, before)) is not None:
        args, err = guard.check(*call)
        if args is None:  # a cap or the order stops the rule
            break
        await execute(ctx, guard, call[0], args, defaults, by="Fixed plan")
        n += 1
    return n
