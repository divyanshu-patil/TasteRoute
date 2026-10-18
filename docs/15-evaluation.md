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
