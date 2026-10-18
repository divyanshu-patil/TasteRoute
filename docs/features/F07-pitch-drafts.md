# F07. Pitch drafts and approval

## Purpose

Write one short, specific pitch email per selected venue that has a contact, using **only stored evidence**, and let the user edit and approve each one.

## How it works

1. **Input bundle per venue** (built by code, not the LLM): brand profile, best product and its label, the venue's name and type, the reason text, up to 4 evidence items with ids, the contact's role, the user's sender name and sign-off.
2. **Generate.** The agent calls the LLM with `pitch_email.md` (temperature `LLM_TEMPERATURE_WRITING`). Output schema:
   ```json
   {"subject": "string <= 80 chars", "body": "string <= 900 chars", "cited_evidence_ids": ["string"]}
   ```
   Prompt rules: address the venue by name; one sentence on the taste match citing at least one evidence item; one sentence on the product; a clear small ask (send a sample, a 10-minute tasting); include the opt-out line; no claims, numbers or names not in the bundle; no pressure tactics; plain text.
3. **Grounding validator** (`grounding.py`):
   - Every id in `cited_evidence_ids` must belong to this venue's evidence.
   - Every capitalised name or brand in the body must appear in the bundle (venue name, brand name, product names, tags, the contact role, the user's name).
   - Any digit sequence in the body must appear in the bundle.
   - The opt-out line must be present.
   - Length limits enforced.
4. If validation fails, regenerate once with the errors. If it fails again, use the **template draft** built from the bundle and label it `template`.
5. **Duplicate protection.** One draft per (run, venue, contact). Re-generating replaces the previous draft only if it is not approved.
6. **Approval state machine:** `draft` → `edited` → `approved` → `exported`. Editing an approved draft moves it back to `edited`. Only `approved` drafts can be exported.

## Opt-out line (default, editable in settings)

"If you'd rather not hear from me, reply 'no thanks' and I won't contact you again."

## Outputs and storage

`drafts` rows: run_id, venue_id, contact_id, subject, body, cited_evidence_ids, source (`llm` or `template`), status, model, prompt_version, created_at, updated_at, approved_at.

## UI

Outreach page: a draft card per venue with subject and body editors, evidence chips (click to open), status pill, Approve button, "Regenerate" button (disabled when approved), "template" label when applicable.

## Tests

| What | How |
|---|---|
| Validator rejects an invented venue, brand, number, missing opt-out, unknown evidence id | Unit tests |
| Repair once, then template fallback | Unit tests with `FakeProvider` |
| State machine transitions, including edit-after-approve | Unit tests |
| One draft per (run, venue, contact); regenerate does not create duplicates | Integration test |
| Suppressed contact never gets a draft | Integration test |
| LLM calls per run within the cap | Integration test |

Acceptance: DRF-01 to DRF-06, LLM-04, LLM-05, REL-03.
