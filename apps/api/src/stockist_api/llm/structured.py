"""Prompt-and-validate JSON (Ollama Cloud has no structured outputs): extract, validate, one repair, then raise."""

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from ..errors import LLMBadResponse

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> Any:
    m = FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


def parse[T: BaseModel](text: str, model: type[T]) -> T:
    return model.model_validate(extract_json(text))


async def structured[T: BaseModel](llm: Any, model: type[T], system: str, user: str, **chat_kwargs: Any) -> T:
    """llm is llm.LLM. Exactly one repair attempt (LLM-04)."""
    schema = json.dumps(model.model_json_schema())
    sys = f"{system}\n\nReturn only one JSON object matching this JSON Schema:\n{schema}"
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
    r = await llm.chat(messages, **chat_kwargs)
    try:
        return parse(r.content, model)
    except (ValueError, ValidationError) as e:
        error = str(e)[:1500]
    from .prompts import load

    repair_prompt, version = load("repair_json")
    kwargs = {**chat_kwargs, "purpose": "repair", "prompt_version": version}
    repair = [
        {"role": "system", "content": repair_prompt + "\n\nJSON Schema:\n" + schema},
        {"role": "user", "content": f"Invalid output:\n{r.content[:4000]}\n\nErrors:\n{error}"},
    ]
    r2 = await llm.chat(repair, **kwargs)
    try:
        return parse(r2.content, model)
    except (ValueError, ValidationError) as e:
        raise LLMBadResponse(f"Invalid JSON after one repair: {str(e)[:200]}") from e
