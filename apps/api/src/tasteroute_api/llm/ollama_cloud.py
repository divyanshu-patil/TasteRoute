"""Ollama Cloud (https://ollama.com/api/chat) with Gemma 4. Verified in docs/llm-contract.md."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..errors import LLMUnavailable
from .base import LLMResult, ToolCall


class OllamaCloudProvider:
    name = "ollama_cloud"
    supports_tools = True

    def __init__(self, *, base_url: str, api_key: str, model: str, http: httpx.AsyncClient | None = None) -> None:
        self.model = model
        self.api_key = api_key
        self.http = http or httpx.AsyncClient(base_url=base_url)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> LLMResult:
        if not self.api_key:
            raise LLMUnavailable("OLLAMA_API_KEY is not set")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            body["tools"] = tools
        for attempt in range(2):  # one retry on 5xx or timeout
            try:
                r = await self.http.post(
                    "/api/chat", json=body, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=timeout
                )
            except httpx.TimeoutException as e:
                if attempt:
                    raise LLMUnavailable("LLM timed out") from e
                continue
            except httpx.TransportError as e:
                raise LLMUnavailable(f"LLM unreachable ({type(e).__name__})") from e
            if r.status_code >= 500 and not attempt:
                await asyncio.sleep(1)
                continue
            if r.status_code != 200:
                raise LLMUnavailable(f"LLM returned {r.status_code}")
            data = r.json()
            msg = data.get("message") or {}
            calls = [
                ToolCall(
                    id=c.get("id") or f"call_{i}",
                    name=(c.get("function") or {}).get("name", ""),
                    arguments=(c.get("function") or {}).get("arguments") or {},
                )
                for i, c in enumerate(msg.get("tool_calls") or [])
            ]
            return LLMResult(
                content=msg.get("content") or "",
                tool_calls=calls,
                model=data.get("model", self.model),
                provider=self.name,
                usage={"input_tokens": data.get("prompt_eval_count", 0), "output_tokens": data.get("eval_count", 0)},
            )
        raise LLMUnavailable("LLM failed after retry")

    async def stream(
        self, messages: list[dict[str, Any]], *, temperature: float, max_tokens: int, timeout: float
    ) -> AsyncIterator[str | dict[str, int]]:
        """NDJSON from /api/chat with stream=true: one {"message": {"content"}} per chunk, then "done" with the counts."""
        if not self.api_key:
            raise LLMUnavailable("OLLAMA_API_KEY is not set")
        body = {"model": self.model, "messages": messages, "stream": True,
                "options": {"temperature": temperature, "num_predict": max_tokens}}
        try:
            async with self.http.stream("POST", "/api/chat", json=body, timeout=timeout,
                                        headers={"Authorization": f"Bearer {self.api_key}"}) as r:
                if r.status_code != 200:
                    raise LLMUnavailable(f"LLM returned {r.status_code}")
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise LLMUnavailable("LLM stream failed")
                    if text := (data.get("message") or {}).get("content"):
                        yield text
                    if data.get("done"):
                        yield {"input_tokens": data.get("prompt_eval_count", 0), "output_tokens": data.get("eval_count", 0)}
        except httpx.TimeoutException as e:
            raise LLMUnavailable("LLM timed out") from e
        except httpx.TransportError as e:
            raise LLMUnavailable(f"LLM unreachable ({type(e).__name__})") from e
