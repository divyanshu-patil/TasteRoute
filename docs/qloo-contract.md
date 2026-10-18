# Qloo contract (verified live, Phase 0, 2026-10-19)

Every fact here comes from a live call against `https://hackathon.api.qloo.com`. Fixtures (compacted, no key) are in `apps/api/tests/fixtures/qloo/`. Compaction (`qloo/compact.py`) keeps only the fields below; stored responses in `qloo_calls.response` are compacted the same way.

## Transport

| Fact | Verified value |
|---|---|
| Base URL | `https://hackathon.api.qloo.com` (staging/prod keys differ; hackathon key returns 401 there) |
| Auth | Header `X-Api-Key: <key>` |
| Method | `GET`, parameters in the query string |
| Typical latency | 1.0–3.7 s for place insights with `take=50` |
| `take` | **1–50**. `take=60` returns `400 {"errors":[{"message":"take must be an integer value between 1 and 50","path":"take"}]}` |
| Invalid parameter value | 400 with `errors[].message` (e.g. a whole query string pasted as `filter.type`) |
| Unknown parameter | Silently ignored (per Qloo hackathon guide) — guards below catch the effects |

## `GET /search` (entity resolution, F02)

Params used: `query`, `types=urn:entity:brand`, `take`.

Response: `{"results": [Entity]}` where Entity has `entity_id`, `name`, `types: ["urn:entity:brand"]`, `popularity` (0–1), `tags[]` (`tag_id`, `name`, `type`), `properties` (`official_site`, `short_description`, `industry`, ...).

**Ordering is not by name match.** `"Partners Coffee"` returns Waitrose & Partners, Starbucks, Blue Bottle. `"Sey Coffee"` returns Starbucks first. Name matching with a threshold (F02, 0.85 token-set ratio) is mandatory.

Resolution results (S3): small brands self-resolve 2/7 (Brooklyn Brewery, Health-Ade as "Health-ade Kombucha"); Partners Coffee, Kings County Distillery, Sey Coffee, Brooklyn Cider House, Mast Brothers do not. Well-known comparables resolve 9/9 (Blue Bottle, Stumptown, La Colombe, Aperol, Campari, Fernet-Branca, GT's Kombucha, Chameleon Cold-brew, Health-Ade).

## `GET /v2/tags` (venue-type tags, F11)

Params: `filter.query`, `filter.tag.types=urn:tag:category:place`, `take`.
Response: `{"success": true, "results": {"tags": [{"id", "name", "type", "parents", "popularity"}]}}`.

| Venue type | Tag id |
|---|---|
| Café / coffee shop | `urn:tag:category:place:coffee_shop` (also `...:cafe`) |
| Bar | `urn:tag:category:place:bar` |
| Restaurant | `urn:tag:category:place:restaurant` |
| Deli | `urn:tag:category:place:deli` |
| Boutique (fashion, secondary) | `urn:tag:category:place:boutique` |

## `GET /v2/insights` for places (F03, F04, F05)

Params used and verified:

| Param | Value | Effect |
|---|---|---|
| `filter.type` | `urn:entity:place` | Required |
| `filter.tags` | venue-type tag id (comma list = union by default) | 50/50 results carry the tag (bar, coffee_shop, deli) |
| `filter.location.query` | locality name, e.g. `Brooklyn` | Resolved locality echoed in `query.localities.filter[0]` (`entity_id`, `name`, `location`, `disambiguation`) |
| `filter.location.radius` | `0` | **Strict boundary.** Without it, results leak ~1–2 km outside (Manhattan venues appeared for `Brooklyn, NY`). With `0`, 50/50 Brooklyn addresses |
| `signal.interests.entities` | comma list of entity ids | Target query. Omitted for the baseline |
| `filter.results.entities` | comma list of place ids | Restricts results to those places; every requested place is scored. Used for per-product fit (F04) |
| `feature.explainability` | `true` | Adds `query.explainability` per entity and aggregate. No extra call |
| `take` | ≤ 50 | |

Response: `{"success": true, "results": {"entities": [Place]}, "query": {...}}`.

Place fields used (after compaction):

| Field | Notes |
|---|---|
| `entity_id`, `name` | |
| `subtype` | `urn:entity:place` (type guard; `type` is `urn:entity`) |
| `location.lat`, `location.lon` | Inside-city guard against the Nominatim bounding box |
| `popularity` | 0–1. **The baseline (no signal) is ordered by this field**; target results also carry it |
| `query.affinity` | 0–1, present only when a signal is sent. Target ordering |
| `query.distance` | metres from the locality |
| `query.explainability["signal.interests.entities"]` | `[{entity_id, score}]` per input entity, normalised 0–1 |
| `tags[]` | `{id, name}`; kinds kept: category, genre, menu_highlight, beverage_offering, customer_identity, interests, ambience, culinary_style, cuisine, specialty_dish, setting, decor, visit_intent, age_range, neighborhood_characteristic |
| `properties.website` | Present for 82–100% of venues per type in Brooklyn (F06 step 1a) |
| `properties.address`, `phone`, `neighborhood`, `price_level`, `business_rating` | |
| `properties.customer_demographics_description` | Qloo's text on who the customers are (evidence, F05) |
| `properties.short_description`, `keywords` | Display only |

Baseline response: same shape, `query.affinity` absent, sorted by `popularity` descending.

## `GET /v2/insights` for tags (audience taste, F05)

`filter.type=urn:tag`, `signal.interests.entities=<ids>`, `filter.parents.types=urn:entity:place`, `take=50` → `results.tags[]` with `id`, `name`, `subtype`, `query.affinity`. Gives the place tags the brand's audience over-indexes on (e.g. Blue Bottle/Stumptown/La Colombe fans → coffee shop, espresso bar, avocado toast, women-owned). Intersected with each venue's tags to write reasons.

## Phase 0 measurements (Brooklyn)

| Spike | Result | Pass? |
|---|---|---|
| S1 coverage | 50 venues per type (café, bar, restaurant, deli) with strict boundary; 100% carry the requested tag; websites 82–100% | Pass |
| S2 brand sensitivity | Café top-20 Jaccard Blue Bottle signal vs energy-drink signal (Red Bull, Monster, Dunkin') **0.176**; bar amaro (Aperol, Campari, Fernet) vs specialty coffee **0.212** | Pass (≤ 0.5) |
| S2 vs baseline | Top-20 Jaccard target vs baseline 0.08–0.21; Spearman on shared venues −0.17 | Pass |
| S3 resolution | Comparables 9/9; small brands 2/7 | Pass |
| S4 explainability | Available on the same call (`feature.explainability=true`), 0 extra calls. Scores are fairly flat (0.28–0.36 for 3 entities) | Known |
| Target/baseline overlap | Only 10–13 of 50 target venues appear in the baseline top 50 | See decision D-03 |

## Errors seen

- `400` take > 50; `400` invalid `filter.type` value.
- Not yet seen live: 401 (wrong key), 403 (unsupported type), 429. Mapped per `04-qloo-integration.md`; covered by respx tests.
