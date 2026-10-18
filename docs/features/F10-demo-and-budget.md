# F10. Demo mode, caching and budget guard

## Purpose

Meet the hackathon rule that judges can test the app **free and without restriction**, without letting public traffic exhaust the Qloo allowance (10,000 calls per month) or Hunter credits.

## Demo mode

1. `scripts/seed_demo.py` runs once with real keys: it creates the demo brand, runs scout and outreach for the demo city, and stores everything under the read-only demo workspace. Its run id goes into `DEMO_RUN_ID`.
2. `/sample` and "See a sample run" load that run: results, venue details, evidence, trace, contacts and drafts.
3. In the demo run, contact emails are shown **masked** (`h***@cafe-example.com`) to avoid republishing contact data; the CSV export of the demo run masks them too.
4. Visitors can edit demo drafts in their browser session only; edits are not saved to the demo run.

## Live runs for visitors

- Anyone can start a live run (no login), limited to `PUBLIC_RUNS_PER_IP_PER_DAY` per IP and per workspace.
- Live runs use the shared cache, so popular brands and cities cost few calls.
- Outreach in live runs is capped by `MAX_OUTREACH_VENUES_PER_RUN` and `HUNTER_MAX_CALLS_PER_RUN`.

## Cache

- Qloo responses cached by a normalised request key (method, path, sorted params) for `QLOO_CACHE_TTL_HOURS`, stored in `qloo_calls` with `cache_key` and `expires_at`. A cache hit creates a trace row with `cache_hit = true` and no network call.
- Overpass results cached 7 days per (city, venue type). Nominatim city lookups cached 30 days. Hunter domain searches cached 14 days per domain.

## Budget guard

- Per-run counters for Qloo, Hunter, Overpass and LLM calls.
- Monthly Qloo counter (sum of live calls in the last 30 days). At 80% of 10,000, new live runs are refused with a friendly message and the sample run is suggested. The owner is warned in logs.
- Hitting a per-run cap stops the current tool, marks remaining work "not checked (limit reached)" and keeps partial results.

## Tests

| What | How |
|---|---|
| Sample run loads with no Qloo, Hunter or Ollama keys set | API test with keys unset |
| Demo emails masked in UI response and CSV | API test |
| IP and workspace limits | API test |
| Identical run makes zero live Qloo calls within TTL | Integration test |
| Monthly guard at 80% | Unit test on the counter query |
| Per-run cap produces partial results and a warning | Integration test |

Acceptance: DMO-01 to DMO-05, QLO-06.
