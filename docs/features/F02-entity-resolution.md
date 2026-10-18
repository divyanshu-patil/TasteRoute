# F02. Product and comparable resolution

## Purpose

Connect each product to **Qloo entities** that represent its taste: the product or brand itself if Qloo knows it, otherwise up to 3 comparable well-known brands or products.

## User story

As a founder of a small brand that Qloo has never heard of, I still get a meaningful ranking because the app finds well-known brands with a similar taste profile and lets me approve them.

## How it works

1. **Search the product itself.** `/search` with the product or brand name and the entity types allowed by the category pack (for Food and drink: brands and, if verified, products or places for a café-brand). Keep the top results.
2. **Accept a match** only when a normalised name similarity is at or above `0.85` (lowercase, strip punctuation and words such as "the", "co", "ltd"; token-set ratio). Otherwise mark it `unresolved`.
3. **Suggest comparables.** If the product is unresolved, the agent asks the LLM (`suggest_comparables.md`) for up to 5 **names** of widely known brands with a similar taste and price tier, given the brand profile. The LLM returns names only, never ids.
4. **Resolve comparables.** Each suggested name goes through steps 1–2. Keep up to 3 that resolve. Unresolved suggestions are listed as dropped.
5. **User review.** The user sees, per product, the resolved entities with Qloo names and types, can remove any, and can search Qloo directly to add one.
6. **Minimum to run:** at least one resolved entity per product that will be ranked, and at least one product overall.

## Outputs and storage

- `product_entities` rows: product_id, qloo_entity_id, name, type, role (`self` or `comparable`), similarity, source call id.
- `qloo_calls` rows for every search.

## Qloo calls

`/search` per name. Budget: at most 5 products × (1 + 5 suggestions) = 30 calls in the worst case; cached for `QLOO_CACHE_TTL_HOURS`.

## Failure handling

| Failure | Behaviour |
|---|---|
| Nothing resolves for a product | Product is excluded from ranking, with a message |
| Nothing resolves for any product | Run cannot start: "Qloo doesn't know these products or similar brands yet" |
| Qloo error | Retry with backoff (3 attempts), then fail this step with `qloo_unavailable` |
| Silent failure (response ignores the requested type) | Treat as no match and log a warning |

## UI

Products step in the wizard: one card per product showing "Qloo knows this" or "Using similar brands", entity chips with type labels, remove buttons, and a Qloo search box.

## Tests

| What | How |
|---|---|
| Name normalisation and threshold accept "Blue Bottle Coffee" for "blue bottle", reject "Bottle Blue Gin" | Unit tests |
| LLM suggestions never become entities without a Qloo match | Unit test: fake LLM returns names, respx returns no match, assert nothing stored |
| Cache hit avoids a second live call | Integration test with fake clock |
| Type guard on silent failures | Contract test with a fixture where the response type differs |
| End-to-end resolution through the API | API test with fixtures |

Acceptance: ENT-01 to ENT-05, QLO-04, QLO-06.
