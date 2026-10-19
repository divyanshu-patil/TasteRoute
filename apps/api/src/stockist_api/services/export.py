"""F08: mailto links and CSV for approved drafts. The app never sends email (EXP-04)."""

import csv
import io
from typing import Any
from urllib.parse import quote

MAILTO_BODY_MAX = 1800
CSV_COLUMNS = [
    "rank", "venue_name", "venue_type", "city", "fit", "lift", "confidence", "best_product", "reason",
    "contact_email", "contact_role", "contact_source", "verification_status", "draft_status", "draft_subject", "draft_body",
]
SHORTENED_NOTE = "\n\n[Shortened for your email app. Use Copy email for the full text.]"


def mailto(to: str, subject: str, body: str) -> str:
    enc = quote(body, safe="")
    if len(enc) > MAILTO_BODY_MAX:
        cut = body
        while len(quote(cut + SHORTENED_NOTE, safe="")) > MAILTO_BODY_MAX and cut:
            cut = cut[: max(0, len(cut) - 40)]
        enc = quote(cut.rstrip() + SHORTENED_NOTE, safe="")
    return f"mailto:{quote(to, safe='@')}?subject={quote(subject, safe='')}&body={enc}"


def mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in CSV_COLUMNS})
    return buf.getvalue()
