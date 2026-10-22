"""LLM access. Only files under llm/ may name a provider (LLM-01)."""

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg

from ..errors import LLMUnavailable
from ..settings import Settings
from .base import LLMProvider, LLMResult, ToolCall
from .fake import FakeProvider
from .ollama_cloud import OllamaCloudProvider

__all__ = ["LLM", "LLMProvider", "LLMResult", "ToolCall", "make_provider"]


def make_provider(s: Settings) -> LLMProvider:
    if s.llm_provider == "fake":
        return FakeProvider()
    return OllamaCloudProvider(
        base_url=s.ollama_base_url, api_key=s.ollama_api_key.get_secret_value(), model=s.ollama_model
    )


class LLM:
    """Wraps a provider: per-run cap (LLM-05), timeouts, and an llm_calls trace row per call (no prompts stored)."""

    def __init__(self, provider: LLMProvider, pool: asyncpg.Pool, s: Settings) -> None:
        self.provider = provider
        self.pool = pool
        self.s = s

    @property
    def name(self) -> str:
        return self.provider.name

    @property
    def model(self) -> str:
        return self.provider.model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        prompt_version: str,
        run_id: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = 1200,
    ) -> LLMResult:
        rid = uuid.UUID(run_id) if run_id else None
        if rid:
            used = await self.pool.fetchval("select count(*) from llm_calls where run_id = $1", rid)
            if used >= self.s.llm_max_calls_per_run:
                raise LLMUnavailable(f"LLM call cap of {self.s.llm_max_calls_per_run} per run reached")
        temp = self.s.llm_temperature_tools if temperature is None else temperature
        t = time.perf_counter()
        status, result = "error", None
        detail: dict[str, Any] = {}
        try:
            result = await self.provider.chat(
                messages, tools=tools, temperature=temp, max_tokens=max_tokens, timeout=self.s.llm_timeout_seconds
            )
            status = "ok"
            detail = {"tool_calls": [c.name for c in result.tool_calls]} if result.tool_calls else {}
            return result
        except LLMUnavailable as e:
            detail = {"error": str(e)[:200]}
            raise
        finally:
            usage = (result.usage if result else None) or {}
            await self.pool.execute(
                "insert into llm_calls (run_id, purpose, provider, model, prompt_version, status, duration_ms, "
                "input_tokens, output_tokens, detail) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                rid, purpose, self.provider.name, self.provider.model, prompt_version, status,
                int((time.perf_counter() - t) * 1000), usage.get("input_tokens"), usage.get("output_tokens"), detail,
            )

    async def stream(
        self, messages: list[dict[str, Any]], *, purpose: str, prompt_version: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        """Text chunks as the model writes them; one llm_calls row when the stream ends, however it ends."""
        t = time.perf_counter()
        status, usage, detail = "error", {}, {}
        try:
            async for chunk in self.provider.stream(messages, temperature=temperature, max_tokens=max_tokens,
                                                     timeout=self.s.llm_timeout_seconds):
                if isinstance(chunk, dict):
                    usage = chunk
                else:
                    yield chunk
            status = "ok"
        except LLMUnavailable as e:
            detail = {"error": str(e)[:200]}
            raise
        finally:
            await self.pool.execute(
                "insert into llm_calls (run_id, purpose, provider, model, prompt_version, status, duration_ms, "
                "input_tokens, output_tokens, detail) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                None, purpose, self.provider.name, self.provider.model, prompt_version, status,
                int((time.perf_counter() - t) * 1000), usage.get("input_tokens"), usage.get("output_tokens"), detail,
            )
