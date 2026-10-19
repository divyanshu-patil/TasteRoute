from functools import lru_cache
from pathlib import Path


@lru_cache
def load(name: str) -> tuple[str, str]:
    """Returns (prompt text, version). The first line of each file is `version: <v>`."""
    head, _, body = (Path(__file__).parent / f"{name}.md").read_text().partition("\n")
    return body.strip(), f"{name}@{head.split(':', 1)[1].strip()}"
