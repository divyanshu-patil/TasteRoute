"""Deterministic provider for tests and LLM_PROVIDER=fake.

Scripted replies are returned first, in order (an Exception in the script is raised).
After that it plays the plan: the next tool in `plan_order` that has no result yet, then finish_phase;
plain-text requests get "{}" so callers exercise their fallbacks.
"""

from collections.abc import AsyncIterator
from typing import Any

from .base import LLMResult, ToolCall

PLAN_ORDER = ["resolve_entities", "rank_venues", "match_products", "attach_evidence", "find_contacts", "draft_pitches"]


class FakeProvider:
    name = "fake"
    model = "fake-1"
    supports_tools = True

    def __init__(self, script: list[LLMResult | Exception] | None = None) -> None:
        self.script = list(script) if script is not None else None
        self.calls: list[dict[str, Any]] = []

    async def aclose(self) -> None:
        return None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> LLMResult:
        self.calls.append({"messages": messages, "tools": tools})
        if self.script:
            nxt = self.script.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        if not tools:
            return LLMResult(content="{}", model=self.model, provider=self.name)
        available = [t["function"]["name"] for t in tools]
        done = {m.get("tool_name") for m in messages if m.get("role") == "tool"}
        for name in PLAN_ORDER:
            if name in available and name not in done:
                return LLMResult("", [ToolCall(f"fake_{name}", name, {})], self.model, self.name)
        return LLMResult("", [ToolCall("fake_finish", "finish_phase", {"summary": "Done."})], self.model, self.name)

    async def stream(
        self, messages: list[dict[str, Any]], *, temperature: float, max_tokens: int, timeout: float
    ) -> AsyncIterator[str | dict[str, int]]:
        """The next scripted reply (or "{}"), a word at a time."""
        r = await self.chat(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
        for i, word in enumerate(r.content.split(" ")):
            yield word if i == 0 else f" {word}"
        yield {"input_tokens": 0, "output_tokens": 0}
