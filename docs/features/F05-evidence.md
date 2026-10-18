# F05. Evidence and explanations

## Purpose

Give every ranked venue a short, honest **reason** and a set of evidence items that trace back to the calls that produced them, so the user (and judges) can check every claim.

## Evidence types

| Type | Source | Label in UI |
|---|---|---|
| `qloo_affinity` | Target and baseline percentiles, lift | "Qloo data" |
| `qloo_explanation` | Qloo explainability output for the venue against the signal entities (if the verified contract provides it) | "Qloo explanation" |
| `qloo_tag_overlap` | Tags on the venue that also describe the signal entities (from returned entity tags) | "Qloo tags" |
| `osm_fact` | Website, email, opening hours from OpenStreetMap | "OpenStreetMap" |
| `contact_source` | Hunter sources (URI, last seen) | "Hunter" |
| `inference` | Anything the app concludes, such as the best product | "Our inference" |

Facts and inferences are always visually distinct.

## How it works

1. After F03 and F04, for the top N venues (default 30), request Qloo explainability for the venue against the run's signal entities if the verified API supports it (Phase 0 decides the exact call). Otherwise build the reason from tag overlap.
2. **Reason text** is assembled by a template from evidence, for example: "Guests here over-index on specialty coffee and natural wine (Qloo). Product B fits best (our inference)." The LLM is **not** used to write the reason, so it cannot introduce unsupported claims.
3. Each evidence item stores the id of the `qloo_calls` or `external_calls` row it came from, and a `captured_at` time.
4. Evidence older than 30 days is marked stale in the UI.

## Outputs and storage

`venue_evidence` rows per run: venue_id, type, label, value (JSON), source_call_id, captured_at.

## UI

Results row shows the reason. Venue detail shows all evidence items with source chips that open the matching trace row.

## Tests

| What | How |
|---|---|
| Every venue shown has at least one Qloo evidence item and a reason | API test over a fixture run |
| Every evidence item's source id exists in the trace | Integration test |
| Template reason uses only tags present in the evidence | Unit test |
| Inference items are labelled as inference | Unit test on the serializer |
| Stale flag after 30 days | Unit test with fake clock |

Acceptance: EVD-01 to EVD-03.
