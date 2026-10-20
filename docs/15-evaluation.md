# 15. Evaluation: does Qloo make the recommendations better?

The judges' first criterion asks how thoroughly and skillfully the project uses Qloo, and Qloo's page says a submission that works the same without Qloo is the wrong thing. This evaluation proves (or disproves) that Qloo changes and improves the output. Report the result honestly, including where it did not help.

## Setups compared

| Setup | How venues are ranked |
|---|---|
| **A. Qloo on** | The full app: target, baseline, lift, fit (F03) |
| **B. Popularity only** | Qloo baseline query only (no taste signal): rank by baseline percentile |
| **C. No Qloo** | OpenStreetMap venues of the same types in the same bounding box, ranked by the LLM from the venue's name, type and any OSM tags, given the brand profile |

B shows the value of the taste signal over popularity. C shows the value of Qloo over a plausible LLM-only product.

## Data

- Demo city, 2 brands with different tastes (for example a specialty coffee roaster and a mainstream soft-drink-style product), food and drink pack, café and bar types.
- For each brand and setup, take the top 15 venues.

## Metrics

1. **Difference:** Jaccard overlap of top 15 between A and B, and between A and C. Lower overlap means Qloo changes the decision. Report Spearman correlation on shared venues.
2. **Brand sensitivity:** Jaccard overlap of A's top 15 for brand 1 versus brand 2. It must be low; if both brands get the same list, the taste signal is not working.
3. **Blind preference:** for each brand, build 10 pairs (a venue from A's top 15 that is not in C's top 15, against one from C's that is not in A's), shuffle the labels, and ask a judge who knows the city's food and drink scene (or, if none is available, the builder using the venues' own websites and menus) "Which venue is a better fit for this product?". Record wins for A.
4. **Reason quality:** for 10 venues in A, check that the Qloo-derived reason is consistent with the venue's own website or menu (yes, partly, no).

## Targets (for the demo claim)

- A vs C overlap ≤ 0.4 and brand 1 vs brand 2 overlap ≤ 0.5.
- A preferred in at least 7 of 10 blind pairs per brand.
- Reasons consistent (yes or partly) for at least 8 of 10.

If a target is missed, the README and video say so, and the claim becomes "a taste-informed starting list" instead of "better targeting".

## Procedure

1. `uv run python scripts/evaluate.py --brand <id> --city <id> --types cafe,bar --out docs/evaluation-results.md`
2. The script runs A and B from cached Qloo data, runs C with the configured LLM, computes metrics 1–2, and writes blind pairs to `evaluation_pairs.csv` with hidden labels.
3. The judge fills the CSV. `scripts/evaluate.py --score evaluation_pairs.csv` computes metric 3 and appends it to the results file.
4. Fill metric 4 manually in the results file.
5. Store a summary in the `evaluations` table.

## Limits of this evaluation

Small samples, one city, a single human judge, and no sales outcomes. It shows whether Qloo changes and plausibly improves targeting, not whether it increases sales. Say this in the README.

## Stockist backtest (pre-registered 2026-10-20, before any test-brand ranking was run)

The A-vs-C test above has no answer key. This one does: real venues that already carry a real brand. The question is the product's question: **given a brand's description and a few well-known comparable brands, which venues in the city carry it?** Brooklyn, food and drink pack.

### Brands and split

Six real brands with public, machine-readable account lists. Lists were opened only to check that they exist and are big enough; no ranking was run before this section was committed. Two **dev** brands may be used to debug and tune the pipeline; the four **test** brands are run once with the frozen pipeline.

| Brand | Split | What it is (as given to every method; no brand name) | Venue types | Ground-truth source |
|---|---|---|---|---|
| Kings County Distillery | dev | A small-batch distillery making bourbon, rye and moonshine | bar, restaurant | stockist.co map on the brand's "where to find us" page |
| Wölffer Estate | dev | A Long Island estate making rosé wines and dry rosé cider | bar, restaurant | Distributor sales locator on the brand's "find us" page (accounts with a recorded sale) |
| Steven Graf Wine | test | An importer of low-intervention wines from small European and American growers | bar, restaurant | "Our Partners: New York Restaurants & Bars" page |
| Parlor Coffee | test | A Brooklyn specialty coffee roaster supplying cafés and restaurants | cafe, restaurant | Storemapper map on the brand's "where to find us" page |
| St. Agrestis | test | Non-alcoholic bottled aperitivo cocktails and a booze-free amaro | bar, restaurant | stockist.co map on the brand's "find" page |
| Casamara Club | test | Non-alcoholic botanical sodas inspired by Italian amari | bar, restaurant, deli | stockist.co map on the brand's "find" page |

Only accounts with a Brooklyn address count. Retail-only accounts (liquor and grocery stores) stay in the list; they drop out at resolution if Qloo does not tag them with one of the brand's venue types (below), the same rule for every method.

### Comparables (fixed now; never the brand itself)

Each is resolved with Qloo `/search` and the app's name match. If one does not resolve, the next backup in order is used; at least 3 must resolve.

| Brand | Comparables | Backups |
|---|---|---|
| Kings County Distillery | Widow Jane, Hudson Whiskey, Woodford Reserve, Bulleit | Maker's Mark |
| Wölffer Estate | Whispering Angel, Château Miraval, Kim Crawford | Angry Orchard |
| Steven Graf Wine | Gut Oggau, Martha Stoumen, Broc Cellars, Kermit Lynch Wine Merchant | Scribe Winery, Donkey & Goat |
| Parlor Coffee | Stumptown Coffee Roasters, Blue Bottle Coffee, Counter Culture Coffee, Intelligentsia Coffee | La Colombe Coffee Roasters |
| St. Agrestis | Ghia, Lyre's, Seedlip, Campari | Aperol |
| Casamara Club | Fever-Tree, Q Mixers, Spindrift, Sanpellegrino | Ghia |

### Resolution and pool

1. **Stockists to Qloo places.** Each Brooklyn account is matched first against the pool by name (the app's 0.85 name match) and street number, then, if unmatched, with one Qloo `/search` (`types=urn:entity:place`, `filter.location` = Brooklyn's centre, `filter.radius`). A match needs the name match, a point inside Brooklyn's bounding box, the same street number when both sides have one, and one of the brand's venue-type tags. Unresolved accounts are excluded for every method; coverage is reported as "k of n accounts are known to Qloo".
2. **One pool per brand.** For each of the brand's venue types: the top 50 Brooklyn places for the comparables signal, the top 50 for the mass-market signal (the pack's generic brands, D-23), the top 50 by popularity (no signal), plus the resolved stockists. Deduplicated. Saved to `docs/eval/pools/<brand>.json` (ids, names, types, neighbourhood). The comparables' own top 50 are in the pool as hard negatives.

### Methods (each ranks the whole pool)

| Method | How |
|---|---|
| Q-raw | Qloo affinity for the comparables over the pool (`filter.results.entities`, batches of 50) |
| **Q-fit** (TasteRoute) | The app's fit: per venue type, comparables percentile vs mass-market percentile at the same venues, `fit = 0.7·t + 0.3·max(t − g, 0)` |
| POP | Qloo popularity |
| LLM | The app's LLM (Gemma 4 31B), given the description and comparables and the pool's names, types and neighbourhoods; scores 0–100 in batches of 50 (pool order shuffled by a fixed hash); ties broken by the same hash |
| RANDOM | Expected recall = k·N / pool size |

The brand's name is never in a Qloo signal or an LLM prompt.

### Metrics

- **recall@15** and **recall@30**: share of resolved stockists in a method's top k.
- **Mean percentile rank** of stockists: 100 × (1 − (rank − 1)/(N − 1)); random is 50.
- **Long-tail recall@30**: recall over stockists outside POP's top 50, where taste should matter most.
- Aggregate: wins on recall@30 over the 4 test brands, with the number of stockists behind each.

### Success target

**TasteRoute (Q-fit) beats the LLM on recall@30 in at least 3 of the 4 test brands.** The result is published whatever it is, in `docs/evaluation-stockists.md`, with where Qloo lost and why.

### Changes after the dev run (2026-10-20, committed before the test run)

The first dev run showed a flaw in the pool, not in any method. Its non-accounts were all top-50 venues (picked because they score high on Qloo affinity or popularity), while most accounts entered the pool only through `/search` (13 of 16 for Kings County Distillery). Any Qloo score then ranks accounts low by construction: the accounts' mean percentile rank was 23–33 for Q-fit, Q-raw and POP on both dev brands, below random. The LLM is not affected. Fixes:

1. **Pool:** per venue type, Qloo's 500 best-known Brooklyn venues (popularity order, no signal, `page` 1–10 with `take=50`; paging verified to page 10). The comparables' and mass-market top 50s are no longer added.
2. **Accounts:** an account counts only if it is in that pool (the app's name match and the same street number when both have one). `/search` is no longer used. Accounts and other venues are therefore picked the same way, by how well Qloo knows them.
3. **LLM scores** are cached in `docs/eval/llm/` (per prompt version and pool) so the run can be checked without new calls.
4. **Exploratory method Q-fit+LLM** (mean of the two positions) is reported but is not TasteRoute's ranking and not part of the success target.

Nothing else changed: brands, split, comparables, venue types, the Q-fit formula, metrics and target are as pre-registered.

Dev result with the frozen pipeline, for the record. Kings County Distillery (10 accounts in the pool): recall@30 Q-fit 20%, LLM 20%; mean percentile rank Q-fit 59, LLM 87. Wölffer Estate (7 accounts): recall@30 0% for every method; mean percentile rank Q-fit 51, LLM 72. **The LLM is ahead on dev.** Its top 10 reads venue names ("The Whiskey Annex", "Bass & Bourbon"). Both dev brands sell through distributors to ordinary bars, which a name says more about than taste does.
