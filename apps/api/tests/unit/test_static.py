"""Grep checks: LLM-01, CAT-01, EXP-04, SEC-01 (repo side)."""

import re
import subprocess
from pathlib import Path

SRC = Path(__file__).parents[2] / "src" / "stockist_api"
ROOT = Path(__file__).parents[4]


def files(exclude: str) -> list[Path]:
    return [p for p in SRC.rglob("*.py") if exclude not in p.relative_to(SRC).parts]


def test_provider_names_only_under_llm():
    pat = re.compile(r"ollama|gemma|openai|anthropic|gemini", re.I)
    bad = [str(p) for p in files("llm") if pat.search(p.read_text()) and p.name != "settings.py"]
    assert bad == []


def test_category_names_only_in_packs():
    pat = re.compile(r"urn:tag:category|coffee_shop|amenity|food_drink|fashion")
    bad = [str(p) for p in files("categories") if pat.search(p.read_text()) and p.name != "settings.py"]  # flag name only
    assert bad == []


def test_no_email_sending_code_or_dependency():
    pat = re.compile(r"smtplib|aiosmtplib|sendgrid|mailgun|postmark|resend|ses\.send|send_email\(")
    bad = [str(p) for p in SRC.rglob("*.py") if pat.search(p.read_text())]
    deps = (SRC.parents[1] / "pyproject.toml").read_text()
    assert bad == [] and not pat.search(deps)


def test_no_secrets_committed():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert not [f for f in tracked if f.endswith(".env")]
    # Real keys contain digits; documented placeholders (e.g. ALL_CAPS_WORDS) do not.
    secret = re.compile(r"(QLOO_API_KEY|OLLAMA_API_KEY|HUNTER_API_KEY)\s*=\s*(?=[A-Za-z_\-]*\d)[A-Za-z0-9_\-]{16,}")
    hits = []
    for f in tracked:
        p = ROOT / f
        text_file = p.suffix in {".py", ".md", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml", ".example"} and p.is_file()
        if text_file and secret.search(p.read_text(errors="ignore")):
            hits.append(f)
    assert hits == []
