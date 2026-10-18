# F04. Best product per venue

## Purpose

For each ranked venue, decide **which of the user's products to lead with**, so a rep with several products pitches the right one.

## How it works

1. For each product (up to 5), run the **target query** from F03 with only that product's entities as the signal, for the same city and venue types. This gives a per-product percentile for each venue.
2. For each venue in the overall ranking, collect its per-product percentiles. A venue missing from a product's results gets 0 for that product.
3. **Best product** = highest percentile. **Margin** = best minus second best.
4. Labels:
   - `clear` if margin ≥ 0.15
   - `close` if 0.05 ≤ margin < 0.15 (UI shows "lead with A, B also fits")
   - `tie` if margin < 0.05 (UI shows both)
5. With only one product, F04 still runs (1 call per venue type) and the label is `single_product`. This call also feeds the High-confidence rule in F03 (appears for at least 2 entities when products have several entities).

## Outputs and storage

`venue_product_fit` rows per run: venue_id, product_id, percentile, is_best, margin, label.

## Qloo calls

Per product per venue type: 1 call. With 5 products and 4 types: 20 calls. Cached.

## Failure handling

If a per-product query fails after retries, that product is marked `unscored` for the run and the best-product column excludes it, with a notice. The overall ranking (F03) is unaffected.

## UI

"Best product" column with a label; a product filter ("show venues where Product B is best"); on the venue detail page, a small bar list of each product's percentile.

## Tests

| What | How |
|---|---|
| Best product and margin labels at boundaries | Unit tests |
| Missing venue treated as 0 | Unit test |
| A failed product query marks only that product unscored | Integration test with respx returning 500 for one query |
| Product filter returns the right venues | API test |

Acceptance: FIT-01 to FIT-03.
