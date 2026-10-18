# F03. Venue ranking (taste fit with lift over baseline)

## Purpose

Produce a ranked list of venues in one city whose **customers' taste** matches the user's products, corrected for popularity so the list is not simply the busiest places.

## User story

As a founder, I see 40 venues in my city ranked by how well their customers' taste matches my products, with a score I can trust is not just "popular places".

## Inputs

- Resolved entities from F02 (all products combined for the overall ranking).
- City (name, centre point, bounding box from Nominatim, cached).
- Venue types from the category pack (each mapped to Qloo place tag ids discovered in Phase 0).

## How it works

For each selected venue type:

1. **Target query.** Qloo insights for `filter.type=urn:entity:place`, location set to the city (`filter.location` as a WKT point plus radius, or `filter.location.query`, whichever Phase 0 proves reliable), `filter.tags` set to the venue-type tag, and `signal.interests.entities` set to the run's resolved entities. Request up to `MAX_VENUES_PER_RUN` results. Record each venue's Qloo entity id, name, location, tags, any available properties, and its affinity value (field name from the verified contract).
2. **Baseline query.** Same request **without** the interest signal (or with the category's fixed baseline signal, decided in Phase 0). This approximates general popularity for that venue type in that city.
3. **Guard.** Assert every returned entity is a place, inside the requested radius (haversine on returned coordinates, 10% tolerance), and carries the requested tag. Entities failing the guard are dropped and counted in a warning.
4. **Normalise.** Within each query, convert affinity to a percentile rank (0–1) so target and baseline are comparable even if raw scales differ.
5. **Lift.** For venues present in both lists: `lift = target_pct - baseline_pct` (range −1 to 1). Venues only in the target list get `baseline_pct = 0` and are flagged `not_in_baseline`. Venues only in the baseline list are excluded.
6. **Fit score.** `fit = 0.7 * target_pct + 0.3 * max(lift, 0)` (weights are **provisional** and stored with the run so they can be changed and re-scored without new calls).
7. **Confidence.**
   - High: target_pct ≥ 0.8 and lift ≥ 0.15 and the venue appears in results for at least 2 of the run's entities when queried per product (from F04).
   - Medium: target_pct ≥ 0.6 and lift ≥ 0.05.
   - Low: otherwise.
   Thresholds are configuration, shown in the UI tooltip.
8. **Merge venue types**, de-duplicate by Qloo entity id, sort by fit, keep the top `MAX_VENUES_PER_RUN`.
9. **Coverage notice** if fewer than 15 venues survive, or if fewer than 50% of target results also appear in the baseline.

## Outputs and storage

- `venues` rows (one per Qloo place entity, shared across runs, refreshed when seen).
- `venue_scores` rows per run: target_pct, baseline_pct, lift, fit, confidence, flags, scoring_version.
- `qloo_calls` rows for every query.

## Qloo calls

Per venue type: 2 calls (target, baseline). With 4 venue types: 8 calls. Cached.

## Failure handling

| Failure | Behaviour |
|---|---|
| Qloo unavailable or auth error | Scout phase fails (`qloo_unavailable` or `qloo_auth`). No ranking from any other source |
| Empty results for a venue type | Skip that type with a notice |
| All venue types empty | Run fails with `no_venues` and suggests a larger city or different types |
| Guard drops more than 30% of results | Warning on the results page and in the trace |

## UI

Results table: rank, venue name, type, fit (0–100), lift (shown as "+23 vs typical"), confidence badge, best product (from F04), reason (from F05). Filters by type, confidence, product. Map is optional and only if `DESIGN.md` includes one.

## Tests

| What | How |
|---|---|
| Percentile normalisation, lift and fit maths | Unit tests with crafted inputs |
| Lift ordering differs from raw target ordering on a crafted fixture | Unit test (proves the baseline matters) |
| Confidence boundaries | Unit tests at each threshold |
| Radius and type guard | Contract test with a fixture containing out-of-radius and wrong-type entities |
| Re-scoring with new weights uses stored responses and makes zero new calls | Integration test |
| Same inputs and cache give identical rankings across LLM providers | Integration test (`LLM_PROVIDER=fake` vs a second fake) |

Acceptance: RNK-01 to RNK-06, QLO-01 to QLO-05, LLM-02.
