"""F07: grounded pitch drafts, one per (run, venue, contact); approval state machine."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from ..agent.context import RunContext
from ..errors import AppError, LLMBadResponse, LLMUnavailable
from ..grounding import Bundle, validate
from ..llm.prompts import load
from ..llm.structured import parse, structured
from .contacts import is_suppressed, suppression_sets

TRANSITIONS = {
    "draft": {"edited", "approved"},
    "edited": {"edited", "approved"},
    "approved": {"edited", "exported", "approved"},
    "exported": {"edited", "exported"},
}


class DraftLocked(AppError):
    code, status, title = "draft_locked", 409, "Approved drafts cannot be regenerated"


class PitchOut(BaseModel):
    subject: str = Field(max_length=120)
    body: str = Field(max_length=1600)
    cited_evidence_ids: list[str] = Field(default_factory=list)


def next_status(current: str, *, edited: bool, approve: bool, export: bool = False) -> str:
    """Editing an approved or exported draft moves it back to 'edited' (DRF-04)."""
    if export:
        if current != "approved" and current != "exported":
            raise AppError("Only approved drafts can be exported", code="draft_not_approved", status=409)
        return "exported"
    if approve:
        return "approved"
    if edited:
        return "edited"
    return current


def short_name(name: str) -> str:
    """'White Noise Coffee - Coffee Shop & Roastery' -> 'White Noise Coffee' (listing suffixes read badly in a greeting)."""
    return re.split(r" [-|–] ", name, maxsplit=1)[0].strip() or name


def evidence_text(e: dict[str, Any]) -> str:
    v = e["value"]
    if e["type"] == "qloo_tag_overlap":
        return "Guests over-index on " + ", ".join(v.get("tags", []))
    if e["type"] == "qloo_explanation":
        return "Fans of " + ", ".join(d["name"] for d in v.get("drivers", [])) + " like this venue"
    if e["type"] == "qloo_venue_profile":
        return "Crowd: " + ", ".join(v.get("crowd", [])) + ". Interests: " + ", ".join(v.get("interests", []))
    return str(e["label"])


async def build_bundle(ctx: RunContext, venue: dict[str, Any], contact: dict[str, Any]) -> Bundle:
    ev = await ctx.pool.fetch(
        "select id, type, label, value from venue_evidence where run_id = $1 and venue_id = $2 "
        "and type in ('qloo_tag_overlap','qloo_explanation','qloo_venue_profile','inference') order by type",
        ctx.rid, venue["venue_id"],
    )
    best = await ctx.pool.fetchrow(
        "select p.name from venue_product_fit f join products p on p.id = f.product_id "
        "where f.run_id = $1 and f.venue_id = $2 and f.is_best", ctx.rid, venue["venue_id"],
    )
    profile = ctx.brand.get("profile") or {}
    vt = ctx.pack.venue_type(venue["venue_type"])
    return Bundle(
        venue_name=short_name(venue["name"]),
        venue_type=vt.label if vt else venue["venue_type"],
        brand_name=ctx.brand["name"],
        sender_name=profile.get("sender_name") or f"The {ctx.brand['name']} team",
        product_names=[p["name"] for p in ctx.products.values()],
        best_product=best["name"] if best else next(iter(ctx.products.values()))["name"],
        reason=venue.get("reason") or "",
        evidence={str(e["id"]): evidence_text(dict(e)) for e in ev},
        contact_role=contact.get("role"),
        ask_examples=ctx.pack.pitch_style.ask_examples,
        opt_out_line=ctx.svc.settings.opt_out_line,
        extra_terms=["Qloo", profile.get("one_liner") or "", " ".join(profile.get("style_words") or []),
                     ctx.city.get("name", ""), " ".join(str(p.get("kind") or "") for p in ctx.products.values())],
    )


def template_draft(b: Bundle) -> PitchOut:
    """Built only from the bundle, so it always passes the validator."""
    prefs = ("Guests over-index", "Crowd", "Fans of")
    cite = sorted((i for i, t in b.evidence.items() if t.startswith(prefs)),
                  key=lambda i: next(n for n, p in enumerate(prefs) if b.evidence[i].startswith(p)))[:1]
    taste = b.evidence[cite[0]] if cite else ""
    if taste.startswith(("Guests", "Crowd")):
        taste = taste.lower()
    taste_line = (
        f"Taste data from Qloo suggests your guests are a natural fit for us: {taste}."
        if taste else "Taste data from Qloo suggests your guests are a natural fit for us."
    )
    body = (
        f"Hi {b.venue_name} team,\n\n"
        f"I'm {b.sender_name} from {b.brand_name}. {taste_line}\n\n"
        f"I think {b.best_product} would suit {b.venue_name}. Could I {b.ask_examples[0]}?\n\n"
        f"Thanks,\n{b.sender_name}\n\n{b.opt_out_line}"
    )
    return PitchOut(subject=f"{b.best_product} for {b.venue_name}"[:80], body=body,
                    cited_evidence_ids=cite or list(b.evidence)[:1])


async def write_pitch(ctx: RunContext, b: Bundle) -> tuple[PitchOut, str, str | None, str | None]:
    """Returns (draft, source, model, prompt_version). One grounding retry, then the template (DRF-03)."""
    prompt, version = load("pitch_email")
    bundle_json = json.dumps({
        "venue_name": b.venue_name, "venue_type": b.venue_type, "brand_name": b.brand_name, "sender_name": b.sender_name,
        "lead_product": b.best_product, "other_products": [p for p in b.product_names if p != b.best_product],
        "evidence": [{"id": i, "text": t} for i, t in b.evidence.items()], "contact_role": b.contact_role,
        "ask_examples": b.ask_examples, "opt_out_line": b.opt_out_line,
    }, ensure_ascii=False)
    kwargs: dict[str, Any] = {"purpose": "pitch", "prompt_version": version, "run_id": ctx.run_id,
                              "temperature": ctx.svc.settings.llm_temperature_writing, "max_tokens": 700}
    try:
        out = await structured(ctx.svc.llm, PitchOut, prompt, f"<bundle>{bundle_json}</bundle>", **kwargs)
        errors = validate(out.subject, out.body, out.cited_evidence_ids, b)
        if errors:
            msgs = [
                {"role": "system", "content": prompt + "\nReturn only one JSON object with subject, body, cited_evidence_ids."},
                {"role": "user", "content": f"<bundle>{bundle_json}</bundle>"},
                {"role": "assistant", "content": out.model_dump_json()},
                {"role": "user", "content": "Fix these problems and return the corrected JSON only: " + "; ".join(errors)},
            ]
            r = await ctx.svc.llm.chat(msgs, **kwargs)
            out = parse(r.content, PitchOut)
            errors = validate(out.subject, out.body, out.cited_evidence_ids, b)
        if not errors:
            return out, "llm", ctx.svc.llm.model, version
    except (LLMUnavailable, LLMBadResponse, ValueError):
        pass
    except Exception as e:  # pydantic ValidationError from parse()
        if type(e).__name__ != "ValidationError":
            raise
    return template_draft(b), "template", None, None


async def draft_pitches(ctx: RunContext, venue_ids: list[str]) -> dict[str, Any]:
    rows = await ctx.pool.fetch(
        "select vs.venue_id, vs.venue_type, vs.reason, v.name, c.id as contact_id, c.email, c.role "
        "from venue_scores vs join venues v on v.id = vs.venue_id "
        "join contacts c on c.run_id = vs.run_id and c.venue_id = vs.venue_id and c.is_primary "
        "where vs.run_id = $1 and vs.venue_id = any($2::uuid[]) order by vs.rank",
        ctx.rid, [uuid.UUID(v) for v in venue_ids],
    )
    sup_e, sup_d = await suppression_sets(ctx.pool, ctx.workspace_id)
    sem = asyncio.Semaphore(4)
    counts = {"llm": 0, "template": 0, "skipped_approved": 0, "suppressed": 0}

    async def one(r: Any) -> None:
        if is_suppressed(r["email"], sup_e, sup_d):
            counts["suppressed"] += 1
            return
        existing = await ctx.pool.fetchval(
            "select status from drafts where run_id = $1 and venue_id = $2 and contact_id = $3",
            ctx.rid, r["venue_id"], r["contact_id"])
        if existing in ("approved", "exported"):
            counts["skipped_approved"] += 1
            return
        async with sem:
            b = await build_bundle(ctx, dict(r), dict(r))
            out, source, model, version = await write_pitch(ctx, b)
        counts[source] += 1
        await ctx.pool.execute(
            "insert into drafts (workspace_id, run_id, venue_id, contact_id, subject, body, cited_evidence_ids, source, "
            "status, model, prompt_version) values ($1,$2,$3,$4,$5,$6,$7,$8,'draft',$9,$10) "
            "on conflict (run_id, venue_id, contact_id) do update set subject = excluded.subject, body = excluded.body, "
            "cited_evidence_ids = excluded.cited_evidence_ids, source = excluded.source, status = 'draft', "
            "model = excluded.model, prompt_version = excluded.prompt_version, updated_at = now() "
            "where drafts.status not in ('approved','exported')",
            uuid.UUID(ctx.workspace_id), ctx.rid, r["venue_id"], r["contact_id"], out.subject, out.body,
            [uuid.UUID(i) for i in out.cited_evidence_ids], source, model, version,
        )

    await asyncio.gather(*[one(r) for r in rows])
    return {"drafted": counts["llm"] + counts["template"], **{k: v for k, v in counts.items() if v}}
