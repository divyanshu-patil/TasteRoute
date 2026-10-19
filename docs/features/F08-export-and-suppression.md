# F08. Export and suppression

## Purpose

Let the user send approved pitches **from their own email** and keep a do-not-contact list that every part of the app respects.

## Export

1. **Open in email app.** For each approved draft, a `mailto:` link with `to`, `subject` and `body` URL-encoded. Bodies longer than about 1,800 characters after encoding are shortened with a note, because some clients truncate long mailto links; a "Copy email" button always works.
2. **CSV export** of the run: `rank, venue_name, venue_type, city, fit, lift, confidence, best_product, reason, contact_email, contact_role, contact_source, verification_status, draft_status, draft_subject, draft_body`. Only approved drafts include subject and body. UTF-8 with a header row.
3. Exporting sets the draft status to `exported` and records `exported_at`.
4. The app sends nothing on its own. A signed-in user can send one draft at a time from their own Gmail (F12).

## Suppression list

- Entries are an email address or a whole domain, with a reason (`opt_out`, `bounced`, `claimed_email`, `manual`) and a timestamp, per workspace.
- Added manually on the settings page, from a draft card ("Mark as do-not-contact"), or automatically from Hunter 451.
- Checked **before** contact lookups (F06), before draft generation (F07), and before export.
- Suppressed contacts are hidden in exports and drafts and shown as "suppressed" in the outreach list.

## Outputs and storage

`suppressions` rows; `drafts.status` and `exported_at` updates; export events in `run_events`.

## UI

Approve and export bar on the outreach page; settings page for the suppression list (add, remove, search).

## Tests

| What | How |
|---|---|
| mailto encoding (spaces, line breaks, `&`, `?`, non-ASCII) | Unit tests |
| CSV columns, escaping and UTF-8 | Unit test |
| Only approved drafts export | API test |
| Domain suppression blocks every address at that domain | Unit test |
| Suppression checked in F06, F07 and export | Integration tests |

Acceptance: EXP-01 to EXP-04, CON-07.
