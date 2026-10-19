from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    usage: dict[str, int] | None = None


class LLMProvider(Protocol):
    name: str
    model: str
    supports_tools: bool

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> LLMResult: ...

    async def aclose(self) -> None: ...
