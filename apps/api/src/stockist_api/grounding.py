"""Grounding validator for pitch drafts (F07, DRF-02): every name, number and cited id must come from the bundle."""

import re
from dataclasses import dataclass, field

SUBJECT_MAX = 80
BODY_MAX = 900
CAPITALISED = re.compile(r"\b[A-Z][A-Za-z0-9'’&.-]*")
DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
# Common words that may be capitalised (sentence starts, greetings, sign-offs). Not names.
COMMON = {
    "a", "about", "after", "again", "all", "also", "an", "and", "any", "are", "as", "at", "be", "because", "best",
    "but", "by", "can", "cheers", "could", "dear", "do", "does", "drop", "every", "few", "for", "from", "glad", "good",
    "great", "guests", "had", "happy", "have", "hello", "here", "hey", "hi", "hope", "how", "i", "i'd", "i'll", "i'm",
    "i've", "if", "in", "is", "it", "it's", "its", "just", "kind", "let", "let's", "looking", "love", "many", "may",
    "maybe", "more", "most", "my", "no", "not", "of", "on", "one", "or", "our", "please", "quick", "regards", "say",
    "see", "send", "since", "sincerely", "so", "some", "thank", "thanks", "that", "the", "their", "these", "they",
    "this", "those", "to", "too", "warm", "warmly", "we", "we'd", "we're", "we've", "what", "when", "which", "while",
    "who", "why", "will", "with", "would", "yes", "you", "you'd", "you're", "your", "yours", "team", "folks",
    "p.s", "ps", "wholesale", "sample", "samples", "tasting", "free", "menu", "shelf", "customers", "crowd", "taste", "data",
}


@dataclass
class Bundle:
    venue_name: str
    venue_type: str
    brand_name: str
    sender_name: str
    product_names: list[str]
    best_product: str
    reason: str
    evidence: dict[str, str]  # evidence id -> text
    contact_role: str | None
    ask_examples: list[str]
    opt_out_line: str
    best_product_kind: str = ""
    brand_one_liner: str = ""
    extra_terms: list[str] = field(default_factory=list)

    def allowed_text(self) -> str:
        parts = [
            self.venue_name, self.venue_type, self.brand_name, self.sender_name, self.best_product, self.reason,
            self.best_product_kind, self.brand_one_liner,
            self.contact_role or "", self.opt_out_line, *self.product_names, *self.evidence.values(),
            *self.ask_examples, *self.extra_terms,
        ]
        return " ".join(parts).lower()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def validate(subject: str, body: str, cited_ids: list[str], b: Bundle) -> list[str]:
    errors: list[str] = []
    if len(subject) > SUBJECT_MAX:
        errors.append(f"subject longer than {SUBJECT_MAX} characters")
    if len(body) > BODY_MAX:
        errors.append(f"body longer than {BODY_MAX} characters")
    if not cited_ids:
        errors.append("cite at least one evidence id")
    unknown = [i for i in cited_ids if i not in b.evidence]
    if unknown:
        errors.append(f"unknown evidence ids: {unknown}")
    if _norm(b.opt_out_line) not in _norm(body):
        errors.append("missing the opt-out line")
    if b.venue_name.lower() not in body.lower():
        errors.append("must address the venue by its exact name")
    allowed = b.allowed_text()
    allowed_words = set(re.findall(r"[a-z0-9'’&.-]+", allowed))
    for text in (subject, body):
        for tok in CAPITALISED.findall(text):
            w = tok.strip(".-’'").lower()
            if not w or w in COMMON or w in allowed_words:
                continue
            errors.append(f"name or term not in the evidence: {tok}")
        for num in DIGITS.findall(text):
            if num not in allowed:
                errors.append(f"number not in the evidence: {num}")
    return list(dict.fromkeys(errors))
