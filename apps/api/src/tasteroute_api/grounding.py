"""Grounding validator for pitch drafts (F07, DRF-02, DRF-08). It checks exactly this:
- every capitalised word (a name or term) appears in the bundle;
- every number is a whole number token of the bundle ("4" is not allowed by "94");
- no phrase from the pack's claim blocklist ("award-winning", "already stock", "half off"), outside names and the
  pack's own ask examples;
- every sentence about Qloo or guests' tastes quotes at least one evidence value (a tag, a fan brand, a crowd word);
- cited evidence ids exist, the venue's exact name and the opt-out line are there, and the lengths fit."""

import re
from dataclasses import dataclass, field

SUBJECT_MAX = 80
BODY_MAX = 900
CAPITALISED = re.compile(r"\b[A-Z][A-Za-z0-9'’&.-]*")
NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
TASTE_TALK = re.compile(r"\b(qloo|over-?index\w*|guests?|fans?|crowds?|audiences?|tastes?)\b", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
SIGN_OFF = re.compile(r"(?im)^\s*(all the )?best( regards| wishes)?,?\s*$")
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
    "p.s", "ps", "wholesale", "sample", "tasting", "menu", "shelf", "customers", "crowd",
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
    evidence_values: dict[str, list[str]] = field(default_factory=dict)  # evidence id -> quotable values in it
    forbidden_claims: list[str] = field(default_factory=list)
    postal_address: str = ""

    def allowed_text(self) -> str:
        parts = [
            self.venue_name, self.venue_type, self.brand_name, self.sender_name, self.best_product, self.reason,
            self.best_product_kind, self.brand_one_liner,
            self.contact_role or "", self.opt_out_line, *self.product_names, *self.evidence.values(),
            *self.ask_examples, *self.extra_terms, self.postal_address,
        ]
        return " ".join(parts).lower()

    def values(self) -> list[str]:
        return [v for vs in self.evidence_values.values() for v in vs if len(v.strip()) >= 3]


def claim_pattern(phrase: str) -> re.Pattern[str]:
    """Whole words only where the phrase starts or ends with a word character ('#1', '% off' have no boundary there)."""
    p = re.escape(phrase.lower()).replace(r"\ ", r"\s+")
    left = r"\b" if phrase[:1].isalnum() else ""
    right = r"s?\b" if phrase[-1:].isalnum() else ""
    return re.compile(left + p + right, re.I)


def claims(text: str, b: "Bundle") -> list[str]:
    """Blocklisted claim phrases in the text, after removing names and the pack's own asks ('Best Pizza' is a name;
    'send a free sample' is an allowed ask) and a 'Best,' sign-off."""
    t = SIGN_OFF.sub(" ", text)
    for allowed in sorted([b.venue_name, b.brand_name, *b.product_names, *b.ask_examples, b.opt_out_line, b.sender_name],
                          key=len, reverse=True):
        if allowed:
            t = re.sub(re.escape(allowed), " ", t, flags=re.I)
    return [c for c in b.forbidden_claims if claim_pattern(c).search(t)]


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
    allowed_numbers = set(NUMBER.findall(allowed))
    values = [v.lower() for v in b.values()]
    for text in (subject, body):
        for tok in CAPITALISED.findall(text):
            w = tok.strip(".-’'").lower()
            if not w or w in COMMON or w in allowed_words or re.sub(r"['’]s$", "", w) in allowed_words:
                continue
            errors.append(f"name or term not in the evidence: {tok}")
        for num in NUMBER.findall(text):
            if num not in allowed_numbers:
                errors.append(f"number not in the evidence: {num}")
        errors += [f"claim not allowed: {c}" for c in claims(text, b)]
        for sentence in SENTENCE.split(text):
            if TASTE_TALK.search(sentence) and not any(v in sentence.lower() for v in values):
                errors.append(f"unsupported_taste_claim: quote an evidence value in \"{sentence.strip()[:80]}\"")
    return list(dict.fromkeys(errors))
