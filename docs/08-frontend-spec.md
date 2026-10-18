# 08. Frontend specification (Next.js)

**Read `docs/DESIGN.md` before building any screen.** If it starts with `PLACEHOLDER`, build only the API client, generated types, data hooks and state logic, and tell the user the design file is missing. Visual decisions come from `DESIGN.md`; behaviour comes from this file.

## Screens

| Route | Screen | Key elements |
|---|---|---|
| `/` | Landing | One-line pitch, "Start" button, "See a sample run" button, three-step explainer, honest limits line |
| `/start` | Intake wizard, step 1 | Website URL field, "describe instead" toggle, Continue |
| `/start` (step 2) | Brand profile | Editable profile card, product rows (1–5), unsupported banner (Flow D) |
| `/start` (step 3) | Products and comparables | Per product: "Qloo knows this" or "Using similar brands", entity chips, remove, Qloo search to add |
| `/start` (step 4) | City and venue types | City search (debounced), venue type checkboxes from the pack, Start run |
| `/runs/[id]` | Live run then results | Progress steps with Qloo call counter, then the ranked table, filters, select checkboxes, "Find contacts" action |
| `/runs/[id]/venues/[venueId]` | Venue detail | Fit, lift, confidence explainer, per-product fit bars, evidence list with source chips, OSM facts |
| `/runs/[id]/outreach` | Contacts and drafts | Contact status per venue with sources, draft editors, approve, regenerate, export bar |
| `/runs/[id]/trace` | Trace | Table of LLM steps, tool calls, Qloo calls, external calls; filters; params collapsed |
| `/sample` | Demo run | Same as results and outreach pages, read-only, masked emails, "This is stored data" label |
| `/settings/suppression` | Do-not-contact list | Add email or domain, reason, search, remove |

## Results table (the most important screen)

Columns: select, rank, venue, type, fit (0–100), lift ("+23 vs typical"), confidence badge (text plus colour), best product (with label), reason (one line, expandable), contact status.

Controls: venue type filter, confidence filter, product filter, sort by fit or lift, page size 20. A sticky action bar shows "N selected → Find contacts".

Every number has a tooltip explaining it in one sentence. The reason has source chips ("Qloo", "Our inference").

## States (all required)

| State | Behaviour |
|---|---|
| Loading | Skeleton rows; progress steps visible during a run |
| Live progress | Steps tick as SSE events arrive; Qloo call counter increases; cache hits labelled |
| Partial | Warnings above the table (types skipped, guard drops, limit reached) |
| Qloo failure | Full error panel with code and retry; no partial ranking |
| LLM unavailable | Banner; ranking works; drafts labelled "template" |
| Unsupported business | Explanation panel with suggestion; no run button |
| Low coverage | Notice above the table |
| No contact | Row shows "No public business email found" and sources checked |
| Empty filter result | Friendly empty state with "clear filters" |
| Reconnect | SSE auto-reconnect with `Last-Event-ID`; banner if offline |
| Not found | 404 page for unknown runs or other workspaces' runs |

## Data access

- `apps/web/lib/api.ts`: typed fetch wrapper using `packages/contracts`; gets or creates the workspace token (`POST /v1/workspaces/session`, stored in `localStorage` as `ss_ws`, wrapped in try/catch) and sends it as `X-Workspace-Token`; problem-object error handling.
- `apps/web/lib/sse.ts`: EventSource wrapper passing the token as the `token` query parameter, with reconnect and event typing.
- Server components for static pages; client components for the wizard, live progress, tables and editors.
- No Supabase client in the browser. No keys in the bundle.

## Components (add to `packages/ui` when reused)

ConfidenceBadge, ScoreCell (fit and lift with tooltip), SourceChip, EvidenceItem, ProgressSteps, CallCounter, VenueTable, DraftEditor, StatusPill, EmptyState, ErrorPanel, Banner, TraceTable. Reuse existing `button` and `card`.

## Accessibility and quality

- Keyboard path through the whole flow, visible focus, labels on inputs, colour never the only signal.
- Works at 360 px width (table collapses to cards).
- Lighthouse accessibility ≥ 90 on the results and outreach pages.
- No layout shift when results load.

## Copy rules

- Say "taste fit", never "will buy" or "demand".
- Label inferences as "Our inference".
- Always show "Nothing is sent from Stockist Scout. You send approved emails from your own inbox."
