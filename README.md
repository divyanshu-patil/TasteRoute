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
  <img src="./docs/screenshots/results.png" width="100%" alt="Results for the Brooklyn sample run: 60 venues ranked, 12 high confidence, 14 Qloo calls, orchestration by the AI agent, the taste signal brands, filters, a map with the top 10 numbered by rank, and a table of venues with fit, lift, confidence, best product, reason, contact status and the LLM's rank.">
</p>
<p align="center"><sub>The sample run: a fictional Brooklyn drinks maker (cold brew, kombucha, aperitivo), 60 cafés and bars ranked from 14 Qloo calls (9 live, 5 cached). "Take the tour" on the sample walks through every screen.</sub></p>

## What it is

A small food or drink brand needs its first wholesale accounts. Lists of cafés and their emails are easy to find; knowing **which venues' guests already like what you make** is not. TasteRoute answers that with Qloo's taste data about each venue's own customers:

- **Which venues to pitch**, ranked by taste fit, not by how busy they are.
- **Which product to lead with** at each one.
- **Where they are**, on a map numbered by rank, and how far each one is from your business if you set its location.
- **Why**, as a reason built from Qloo's explanation, with every source one click away.
- **A first email** that cites only that evidence, for you to edit, approve and send from your own inbox.

Built for the Qloo Agentic Hackathon 2026 ("Agents, but with taste").

## Why it needs Qloo

| Without Qloo | With TasteRoute |
|---|---|
| Every café in the city, sorted by rating or distance | The venues whose guests over-index on the brands you resemble |
| The busiest places float to the top | Lift compares the same venues against mass-market brands, and chains are hidden by default |
| The same product pitched everywhere | A separate Qloo query per product picks the lead product per venue |
| A generic email | An email that names the specific taste overlap, checked against the evidence |

Switch Qloo off and TasteRoute says it cannot rank venues and stops. It never falls back to guesses.

## How it works

<p align="center">
  <img src="./assets/readme/flow.svg" width="100%" alt="Four screens: paste your website; Qloo resolves your products or similar brands; venues ranked by taste fit and lift; you approve each email. Fit equals 0.7 times taste plus 0.3 times lift.">
</p>

1. **Your brand.** Paste a website (up to 3 pages are read) or describe your products. The LLM drafts a profile you confirm.
2. **Qloo resolves taste.** Each product is looked up with Qloo `/search`. Products too new for Qloo use real comparable brands, each one verified by `/search`. Entity ids only ever come from Qloo.
3. **Rank.** For each venue type, a Qloo `/v2/insights` place query with your brands as the signal and `feature.explainability` gives the **taste** percentile and which of your brands drive it. A second query asks about the same venues (`filter.results.entities`) with mass-market food and drink brands as the signal (Coca-Cola, Pepsi, Budweiser, Starbucks, Dunkin', ids verified with `/search`). `lift = taste − mass-market taste`, `fit = 0.7 × taste + 0.3 × max(lift, 0)`. Chains and the venues of brands you resemble are hidden by default and counted; makers of what you sell, cafés offered an alcoholic product and venues Qloo marks as growing get chips. None of these change a score.
4. **Taste route.** Two Qloo heatmap queries for the city (`filter.type=urn:heatmap`), one with your brands as the signal and one with the mass-market brands, show where your brands' fans concentrate more than everyone's. The top 15 venues are grouped into walkable areas and the strongest hotspot comes first, with the heatmap shaded on the map. It never changes a score.
5. **Evidence and product fit.** One insights query per product with `filter.results.entities` scores every ranked venue for that product; the lead product is the one the venue stands out most for among its type (standardised affinity), and a café or deli leads with a non-alcoholic product when there is one. Audience tags (`filter.type=urn:tag`) and each venue's Qloo tags explain the match. Qloo's cross-domain data adds the music your brands' fans like and how each venue scores with those artists' fans, shown as "Shared tastes beyond food and drink". It explains; it never changes a score, because the pre-registered backtest check found it didn't help (4 test accounts in the top 30 against 8). Reasons label each claim as "Qloo" or "Our inference".
6. **Contacts.** Only public business addresses: the venue's OpenStreetMap listing and its own website, then a web search whose result pages are fetched and read like the venue's own (Hunter domain search when a key is set). An address is kept only when the page parser reads that exact address on the page, including spelled-out forms like "hello [at] cafe [dot] com"; nothing is assembled from hints. A Gmail-style inbox counts only when the page labels it as a contact, and ranks below the venue's own domain. Every contact shows where it was published.
7. **Drafts.** The LLM writes a short pitch from an evidence bundle. A grounding validator checks exactly this: every capitalised name or term is in the bundle; every number is a whole number from the bundle (a "4" is not excused by a "94"); no phrase from the category's claim blocklist (award-winning, organic, already stock, sold out, half off, guaranteed, healthy and so on) outside names and the category's own asks; every sentence about Qloo, guests, fans or taste quotes an evidence value word for word; cited evidence exists; the venue's exact name and the opt-out line are there. After one repair attempt, a template that always passes takes over. Nothing goes out until you approve a draft: log in with Google and "Send with Gmail" sends that one email from your own Gmail ("Send all" sends the approved, unsent drafts after you confirm the count), or copy approved drafts out.

An AI agent (Gemma 4 31B on Ollama Cloud, native tool calls) runs these steps as tools. It gets a goal, tools and decision rules, not a script, and the tool results carry the numbers it decides from. When a product is known through fewer than 2 similar brands, it asks for more (Qloo must confirm each one). When a venue type returns fewer than 15 venues, it adds another type. Each decision appears in the trace with what the agent saw and its reason. A rule checker approves every call: the tool is allowed in this phase, comes in order, uses only ids the run holds, stays within the caps and doesn't repeat. After two invalid steps, an unavailable model or the step limit, a fixed plan applies the same rules and produces identical scores. In three test runs the agent added cafés, then restaurants, in Hudson, NY (8 venues to 21); asked for more brands for two natural wines (Qloo knew none, so the run stopped rather than guess); and needed no decision in Portland, Maine ([`docs/eval/agent-decisions.json`](./docs/eval/agent-decisions.json)).

```mermaid
flowchart LR
  W[Next.js web app] -- HTTPS + SSE --> R[FastAPI routes]
  R --> AG[Agent loop + rule checker]
  AG --> LLM[Gemma 4 31B on Ollama Cloud]
  AG --> T[Tools]
  AG -. fallback .-> DP[Deterministic plan] --> T
  T --> Q[Qloo client: cache, rate limit, budget] --> QL[(Qloo API)]
  T --> S[Scoring: fit, lift, confidence, product fit]
  T --> X[Contacts: OpenStreetMap, venue sites, web search, Hunter]
  T --> G[Grounding validator]
  R --> DB[(Postgres, row-level security)]
  T --> DB
  W -. map tiles .-> OSM[(OpenFreeMap tiles)]
```

Keys stay on the API. The browser calls only FastAPI, plus public map tiles that need no key.

## See every step

<table>
  <tr>
    <td width="50%"><img src="./docs/screenshots/venue.png" alt="Venue detail for Vinegar Hill House: fit 98, lift +94, taste percentile 100, popularity percentile 70 and mass-market taste 6, a reason with Qloo source chips, per-product fit bars, and the music its guests' tastes share with your brands' fans."></td>
    <td width="50%"><img src="./docs/screenshots/outreach.png" alt="Outreach page: contacts with sources checked, an AI draft citing one Qloo fact, and an export bar."></td>
  </tr>
  <tr>
    <td><b>Venue detail.</b> Fit, lift and the percentiles behind them, per-product fit, shared tastes beyond food and drink, each piece of Qloo evidence, and where the venue is.</td>
    <td><b>Outreach.</b> Contacts with their sources, editable drafts, approve, open in mail app, CSV export.</td>
  </tr>
  <tr>
    <td><img src="./docs/screenshots/trace.png" alt="Trace page listing agent steps, LLM calls, Qloo calls with cache hits and web lookups."></td>
    <td><img src="./docs/screenshots/start.png" alt="Start wizard step one: use my website or describe instead, then an optional business location with a search box and a world map to click."></td>
  </tr>
  <tr>
    <td><b>Trace.</b> Every agent step, LLM call, Qloo call and web lookup, in order. Keys never appear.</td>
    <td><b>Start.</b> Four steps: brand and your location (optional, type or click the map), profile, Qloo matches, then city (framed on the map) and venue types.</td>
  </tr>
  <tr>
    <td><img src="./docs/screenshots/tour.png" alt="Guided tour, step 4 of 8: the results map is outlined and a black card explains that the top 10 venues are numbered by rank."></td>
    <td><img src="./docs/screenshots/landing.png" alt="Landing page: Find venues that share your taste, with Start a run and Take the 2-minute tour buttons."></td>
  </tr>
  <tr>
    <td><b>Guided tour.</b> Walks through the sample from results to venue, outreach and trace. Esc or Skip closes it.</td>
    <td><b>Landing.</b> Start a run, or take the tour of the sample run.</td>
  </tr>
</table>

<p align="center">
  <img src="./docs/screenshots/mobile.png" width="100%" alt="At phone width: the landing page, the results map with the guided tour open, and venue detail for Vinegar Hill House.">
</p>

## Does it find real accounts?

A backtest with an answer key, pre-registered in [`docs/15-evaluation.md`](./docs/15-evaluation.md): six real brands' published Brooklyn accounts, two brands to fix the method and four run once. Every method ranks the same pool (Qloo's 500 best-known venues per venue type) and none sees the brand's name. Full tables, every account and the code: [`docs/evaluation-stockists.md`](./docs/evaluation-stockists.md); summary page: `/evaluation`.

| Test brand | Accounts in the pool | TasteRoute (Q-fit) | Qloo taste only | LLM (names, types, neighbourhoods) | Chance |
|---|---|---|---|---|---|
| Parlor Coffee (specialty coffee) | 4 | 0 | 1 | 1 | 0.1 |
| St. Agrestis (non-alcoholic aperitivo) | 36 | 7 | 8 | 7 | 1.2 |
| Casamara Club (botanical sodas) | 7 | 1 | 1 | 0 | 0.2 |
| Steven Graf Wine (natural wine) | not scored: Qloo knows none of its 6 comparables | | | | |

Cells: accounts in each method's top 30.

- **A tie, not a win.** The pre-registered target was TasteRoute beating the LLM on recall@30 in 3 of 4 test brands. It won 1, tied 1, lost 1; the fourth couldn't be scored. The LLM also ranks accounts higher on average (mean percentile rank) on every scored brand.
- **They find different accounts.** Qloo puts Grand Army 9th of 875 for St. Agrestis (fans of Ghia and Campari over-index there); the LLM puts it 284th. The LLM finds venues with the category in their name. So the results page shows both.
- **Lift didn't help here.** Qloo's taste score alone found 10 accounts to Q-fit's 8: the mass-market brands include Starbucks and Dunkin', which pushes real café accounts down for a coffee roaster. Logged as an open decision, not changed after seeing the test.

## Does Qloo change the answer?

`apps/api/scripts/evaluate.py` compares three setups for two fictional brands with different tastes, a specialty coffee roaster and a mainstream cola, in Brooklyn (top 15 cafés and bars each). Full tables: [`docs/evaluation-results.md`](./docs/evaluation-results.md).

| Setup | Coffee roaster | Cola |
|---|---|---|
| **A. TasteRoute** vs **B. Qloo popularity only**, overlap | 0.07 | 0.00 |
| **A** vs **C. No Qloo** (LLM ranks OpenStreetMap venues), overlap | 0.00 | 0.00 |
| A's top 15 that were even in C's candidate pool | 1 | 1 |

- **Brand sensitivity:** the two brands' top-15 lists share 1 venue (a Blue Bottle Coffee), and each reads like its brand. The coffee list mixes restaurant-bars and a hotel bar (Wythe Hotel, Vinegar Hill House), cocktail bars (Clover Club) and specialty cafés (SEY Coffee, Black Brick, Coffee Mob). The cola list is beer halls and dive bars (Fulton Hall, Draft Barn, Dolly's Swing and Dive) and three Starbucks branches. This script shows chains and the brands' own venues, which the app hides by default.
- **Read the A vs C number carefully:** C could only pick from its OSM sample, so most of that difference comes from the candidate pools, not judgement.
- **Still open:** the blind preference test (10 A-only vs C-only pairs per brand, judged from the venues' own sites) and the reason-quality check need a human judge. Until those are scored, the honest claim is "a taste-informed starting list", not "better targeting".

## Guardrails

- **Qloo decides, the LLM narrates.** Venues, scores, product picks and reasons come from Qloo responses. The LLM chooses tools and writes words.
- **Fail closed.** No key, a rejected key or Qloo down: the run stops with an error panel and shows no partial ranking.
- **You approve and send every email.** The app drafts. Nothing goes out until you approve a draft and click Send with Gmail (or confirm Send all for approved drafts), from your own Gmail. Without sign-in, you copy or export approved drafts.
- **Business contacts only.** Contacts are copied from a published page or listing, never built from a pattern. A do-not-contact list removes emails and domains from lookups, drafts and exports.
- **Honest copy.** "Taste fit", never purchase intent. Inferences are labelled.
- **Budgets.** Qloo calls are cached, rate limited, capped per run and per month, and counted on screen.

## Run it locally

Requires Node 24 with pnpm, Python 3.12 with [uv](https://docs.astral.sh/uv/), and Postgres 15.

```bash
pnpm install
cd apps/api && uv sync
cp .env.example .env          # add QLOO_API_KEY and OLLAMA_API_KEY; HUNTER_API_KEY is optional
createdb tasteroute && uv run python scripts/migrate.py
uv run python scripts/seed_demo.py --outreach 15   # optional: builds the sample run with live calls (about 15 Qloo calls, some cached, and 40 LLM calls)
cd ../.. && pnpm dev                 # web on http://localhost:3000, API on http://localhost:8000
```

Open http://localhost:3000/sample?tour=1 for the guided tour of the sample run.

Set `LLM_PROVIDER=fake` to run without an LLM key. Ranking still needs Qloo.

Optional sign-in and Gmail sending (Supabase Auth with Google): set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in `apps/api/.env`, and `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `apps/web/.env.local` (copy `apps/web/.env.example`). Setup on the Supabase and Google side is in [docs/09](docs/09-external-services.md#supabase-auth-and-gmail-f12).

### Tests

```bash
createdb tasteroute_test
(cd apps/api && uv run python scripts/migrate.py --url postgresql://localhost:5432/tasteroute_test)
pnpm turbo lint check-types test
```

167 API tests (pytest) and 21 web tests (Vitest). Tests never call Qloo, the LLM, web search, Supabase, Gmail, OpenStreetMap or Photon: recorded fixtures, a fake model, and a network block stand in. CI runs the same checks on Postgres 15 and fails if `packages/contracts` drifts from the API.

With the API running, `uv run python scripts/e2e_smoke.py` (in `apps/api`) walks the whole judge path over HTTP: intake, Qloo matches, run, ranking, rescore, contacts, drafts, approval, CSV export, do-not-contact, trace. It makes live calls (about 10 Qloo and 15–25 LLM) and prints what it spent.

## Project layout

```text
apps/api            FastAPI: Qloo client, scoring, agent and rule checker (plan guard), outreach, SSE progress
apps/web            Next.js: wizard, live run, results and map, venue detail, outreach, trace, guided tour
packages/contracts  TypeScript types generated from the API's OpenAPI schema
supabase/migrations Postgres schema (row-level security on every table)
docs/               Product brief, architecture, Qloo contract, evaluation, runbook
```

## Limits

- Ranking covers only places Qloo knows. A great venue missing from Qloo never appears.
- One category pack (food and drink) is tuned and tested. The sample brand run the same way in three cities ([`docs/eval/coverage-cities.json`](./docs/eval/coverage-cities.json), 2026-10-20):

  | City | Venues ranked | High confidence | Top 10 with a published contact |
  |---|---|---|---|
  | Brooklyn | 60 | 12 | 9 |
  | Chicago | 60 | 15 | 8 |
  | Los Angeles | 60 | 14 | 8 |

  Smaller towns return fewer venues: Hudson, NY gave 8 bars and delis until the agent added cafés and restaurants (21).
- Contacts depend on what venues publish: 12 of the top 15 in the sample, 8 or 9 of the top 10 in the city runs above. Ranking never depends on them.
- The public demo allows 3 live runs per visitor per day (`PUBLIC_RUNS_PER_IP_PER_DAY`; `0` turns it off locally). The sample run is always free.
- The map uses OpenFreeMap's free vector tiles (OpenStreetMap data), trimmed to food and drink places and famous sights. Distances are straight lines, not travel routes, and your location never changes the ranking.
- Taste fit is a starting list, not a sales forecast.

## Licence

[MIT](./LICENSE)
