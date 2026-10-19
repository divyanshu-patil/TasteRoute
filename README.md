<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="TasteRoute: ranks the cafés and bars in your city by how much their guests share your brand's taste, then drafts the pitch you approve. Shows the top three Brooklyn venues with fit and lift.">
</p>

<p align="center">
  <a href="./docs/evaluation-results.md">Evaluation</a> ·
  <a href="#run-it-locally">Run it locally</a> ·
  <a href="./docs/00-product-brief.md">Product brief</a> ·
  <a href="./LICENSE">MIT licence</a>
</p>

<p align="center">
  <img src="./docs/screenshots/results.png" width="100%" alt="Results for the Brooklyn sample run: 60 venues ranked, 19 high confidence, 11 Qloo calls, the taste signal brands, filters, and a table of venues with fit, lift, confidence, best product, reason and contact status.">
</p>
<p align="center"><sub>The sample run: a fictional Brooklyn drinks maker (cold brew, kombucha, aperitivo), 60 cafés and bars ranked from 11 Qloo calls.</sub></p>

## What it is

A small food or drink brand needs its first wholesale accounts. Lists of cafés and their emails are easy to find; knowing **which venues' guests already like what you make** is not. TasteRoute answers that with Qloo's taste data about each venue's own customers:

- **Which venues to pitch**, ranked by taste fit, not by how busy they are.
- **Which product to lead with** at each one.
- **Why**, as a reason built from Qloo's explanation, with every source one click away.
- **A first email** that cites only that evidence, for you to edit, approve and send from your own inbox.

Built for the Qloo Agentic Hackathon 2026 ("Agents, but with taste").

## Why it needs Qloo

| Without Qloo | With TasteRoute |
|---|---|
| Every café in the city, sorted by rating or distance | The venues whose guests over-index on the brands you resemble |
| The busiest places float to the top | Lift subtracts Qloo's popularity baseline, so busy alone doesn't win |
| The same product pitched everywhere | A separate Qloo query per product picks the lead product per venue |
| A generic email | An email that names the specific taste overlap, checked against the evidence |

Switch Qloo off and TasteRoute says it cannot rank venues and stops. It never falls back to guesses.

## How it works

<p align="center">
  <img src="./assets/readme/flow.svg" width="100%" alt="Four screens: paste your website; Qloo resolves your products or similar brands; venues ranked by taste fit and lift; you approve each email. Fit equals 0.7 times taste plus 0.3 times lift.">
</p>

1. **Your brand.** Paste a website (up to 3 pages are read) or describe your products. The LLM drafts a profile you confirm.
2. **Qloo resolves taste.** Each product is looked up with Qloo `/search`. Products too new for Qloo use real comparable brands, each one verified by `/search`. Entity ids only ever come from Qloo.
3. **Rank.** For each venue type, a Qloo `/v2/insights` place query with your brands as the signal and `feature.explainability` gives the **taste** percentile and which of your brands drive it. The same query without a signal gives the **popularity** baseline. `lift = taste − popularity`, `fit = 0.7 × taste + 0.3 × max(lift, 0)`.
4. **Evidence and product fit.** One insights query per product with `filter.results.entities` scores every ranked venue for that product. Audience tags (`filter.type=urn:tag`) and each venue's Qloo tags explain the match. Reasons label each claim as "Qloo" or "Our inference".
5. **Contacts.** Only public business addresses: the venue's OpenStreetMap listing and its own website (Hunter domain search when a key is set). Every contact shows where it was published.
6. **Drafts.** The LLM writes a short pitch from an evidence bundle. A grounding validator rejects any name, number or claim not in that bundle; after one repair attempt, a template that always passes takes over. Nothing is sent for you.

An AI agent (Gemma 4 31B on Ollama Cloud, native tool calls) runs these steps as tools. A plan guard checks every call's phase, order and arguments. After two invalid steps, an unavailable model or the step limit, a deterministic plan runs the same tools and produces identical scores.

## See every step

<table>
  <tr>
    <td width="50%"><img src="./docs/screenshots/venue.png" alt="Venue detail for Oslo Coffee Roasters: fit 91, lift +85, taste percentile 94, popularity percentile 9, reason with Qloo source chips, per-product fit bars and the Qloo evidence list."></td>
    <td width="50%"><img src="./docs/screenshots/outreach.png" alt="Outreach page: contacts with sources checked, an AI draft citing one Qloo fact, and an export bar."></td>
  </tr>
  <tr>
    <td><b>Venue detail.</b> Fit, lift and both percentiles, per-product fit, and each piece of Qloo evidence.</td>
    <td><b>Outreach.</b> Contacts with their sources, editable drafts, approve, open in mail app, CSV export.</td>
  </tr>
  <tr>
    <td><img src="./docs/screenshots/trace.png" alt="Trace page listing agent steps, LLM calls, Qloo calls with cache hits and web lookups."></td>
    <td><img src="./docs/screenshots/start.png" alt="Start wizard step one: use my website or describe instead."></td>
  </tr>
  <tr>
    <td><b>Trace.</b> Every agent step, LLM call, Qloo call and web lookup, in order. Keys never appear.</td>
    <td><b>Start.</b> Four steps: brand, profile, Qloo matches, city and venue types.</td>
  </tr>
</table>

<p align="center">
  <img src="./docs/screenshots/mobile.png" width="100%" alt="The landing page, results and venue detail at phone width.">
</p>

## Does Qloo change the answer?

`apps/api/scripts/evaluate.py` compares three setups for two fictional brands with different tastes, a specialty coffee roaster and a mainstream cola, in Brooklyn (top 15 cafés and bars each). Full tables: [`docs/evaluation-results.md`](./docs/evaluation-results.md).

| Setup | Coffee roaster | Cola |
|---|---|---|
| **A. TasteRoute** vs **B. Qloo popularity only**, overlap | 0.00 | 0.00 |
| **A** vs **C. No Qloo** (LLM ranks OpenStreetMap venues), overlap | 0.00 | 0.00 |
| A's top 15 that were even in C's candidate pool | 1 | 1 |

- **Brand sensitivity:** the two brands' top-15 lists share 0 venues, and each reads like its brand. The coffee list mixes specialty cafés (White Noise, Kaigo, Coffee Mob, Oslo, Blue Bottle) with restaurant-bars and cocktail bars. The cola list is dive and neighbourhood bars, three Starbucks branches and a bagel shop.
- **Read the A vs C number carefully:** C could only pick from its OSM sample, so most of that difference comes from the candidate pools, not judgement.
- **Still open:** the blind preference test (10 A-only vs C-only pairs per brand, judged from the venues' own sites) and the reason-quality check need a human judge. Until those are scored, the honest claim is "a taste-informed starting list", not "better targeting".

## Guardrails

- **Qloo decides, the LLM narrates.** Venues, scores, product picks and reasons come from Qloo responses. The LLM chooses tools and writes words.
- **Fail closed.** No key, a rejected key or Qloo down: the run stops with an error panel and shows no partial ranking.
- **Humans approve every email.** The app has no mail-sending code. It drafts, you approve, you send.
- **Business contacts only.** Contacts are never constructed or guessed. A do-not-contact list removes emails and domains from lookups, drafts and exports.
- **Honest copy.** "Taste fit", never purchase intent. Inferences are labelled.
- **Budgets.** Qloo calls are cached, rate limited, capped per run and per month, and counted on screen.

## Run it locally

Requires Node 24 with pnpm, Python 3.12 with [uv](https://docs.astral.sh/uv/), and Postgres 15.

```bash
pnpm install
cd apps/api && uv sync
cp .env.example .env          # add QLOO_API_KEY and OLLAMA_API_KEY; HUNTER_API_KEY is optional
createdb tasteroute && uv run python scripts/migrate.py
uv run python scripts/seed_demo.py   # optional: builds the sample run with live calls (about 10 Qloo calls)
cd ../.. && pnpm dev                 # web on http://localhost:3000, API on http://localhost:8000
```

Set `LLM_PROVIDER=fake` to run without an LLM key. Ranking still needs Qloo.

### Tests

```bash
createdb tasteroute_test
(cd apps/api && uv run python scripts/migrate.py --url postgresql://localhost:5432/tasteroute_test)
pnpm turbo lint check-types test
```

103 API tests (pytest) and 9 web tests (Vitest). Tests never call Qloo, the LLM or OpenStreetMap: recorded fixtures, a fake model, and a network block stand in. CI runs the same checks on Postgres 15.

## Project layout

```text
apps/api            FastAPI: Qloo client, scoring, agent and plan guard, outreach, SSE progress
apps/web            Next.js: wizard, live run, results, venue detail, outreach, trace
packages/contracts  TypeScript types generated from the API's OpenAPI schema
supabase/migrations Postgres schema (row-level security on every table)
docs/               Product brief, architecture, Qloo contract, evaluation, runbook
```

## Limits

- Ranking covers only places Qloo knows. A great venue missing from Qloo never appears.
- One demo city (Brooklyn) and one category pack (food and drink) are tuned and tested.
- Contacts cover about half of top venues in the sample (4 of 8), from public listings and venue sites.
- Taste fit is a starting list, not a sales forecast.

## Licence

[MIT](./LICENSE)
