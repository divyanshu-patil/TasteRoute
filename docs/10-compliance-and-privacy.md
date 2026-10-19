# 10. Compliance and privacy

This is engineering guidance, not legal advice. Check the email and data protection rules where your users and recipients are.

## Outreach principles

1. **Human approval.** Every email is written as a draft and approved by the user. Nothing is sent without the user's click, from their own Gmail (F12) or copied out by hand: "Send with Gmail" sends one draft; "Send all" sends the unsent drafts of one run (at most 25 venues) after the user confirms the count. No scheduled or background sending.
2. **Business contacts only.** Contacts come from the venue's own website, its public listing (OpenStreetMap), its own domain (Hunter domain search) or, as a last resort, a web search that keeps only addresses on the venue's domain or carrying its name. Each shows the page it came from. No consumer data, no personal social profiles, no guessed addresses.
3. **Relevance.** Each draft must cite the specific reason the venue fits (grounding validator). No bulk or generic messages.
4. **Opt-out.** Every draft includes an opt-out line. Opt-outs are recorded in the suppression list and honoured everywhere.
5. **Honesty.** No false claims, no fake urgency, no misleading subjects. The sender is the user, using their own email account.
6. **Respect exclusions.** Hunter `451 claimed_email` adds the address to suppression automatically.

## Data the app stores

| Data | Why | Retention |
|---|---|---|
| Brand profile and products | To run rankings | Until the workspace is deleted (60 days inactivity for anonymous workspaces) |
| Website text | Debugging the profile step | 30 days |
| Venue data from Qloo and OpenStreetMap | Ranking and evidence | Cached with expiry; trace rows kept for the run's life |
| Business contacts | Outreach | With the run; deleted with the workspace |
| Drafts | User's work | With the run |
| Suppression list | Never contact again | With the workspace |
| Client IP | Rate limiting | Stored only as a salted hash |
| Account email and Supabase user id (signed-in users) | Keep the workspace across devices | With the workspace |
| Google token for sending | Send the email the user clicked | Never stored: kept in the browser, used for one request |

No passwords, no payment data, no consumer data.

## Security controls

- Keys only in server environment variables. `.env` files are git-ignored.
- RLS enabled on all tables with no public policies; the browser never talks to Supabase's database (only to Supabase Auth to sign in).
- Signed workspace token (HMAC with `SESSION_SECRET`) checked on every request; it grants access only to that anonymous workspace's data. HTTPS only in production.
- SSRF guard on the website reader.
- Input validation on every endpoint; unknown fields rejected.
- Rate limits on runs, intake and search endpoints.
- No full prompts or completions in production logs.
- Dependency audit (`pip-audit`, `pnpm audit`) before submission.

## Third-party terms

- Use Qloo, Hunter, OpenStreetMap services and Ollama Cloud within their terms. OpenStreetMap data requires attribution (ODbL).
- Do not resell or republish third-party data. The demo run masks contact emails.
- Hackathon rule: the entrant must be authorised to use third-party tools under their terms.

## Open-source licence

The repo must include a `LICENSE` file (hackathon rule). MIT or Apache-2.0 are simple choices. Check that dependencies' licences are compatible.
