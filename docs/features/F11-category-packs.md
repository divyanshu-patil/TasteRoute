# F11. Category packs

## Purpose

Keep the engine general while shipping one category in depth. A **category pack** is a small config file that tells the engine which Qloo entity types describe the seller's products, which place types count as prospects, and how to word the pitch.

## Pack format (`apps/api/src/stockist_api/categories/food_drink.yaml`)

```yaml
id: food_drink
label: Food and drink
status: full                # full | secondary | roadmap
product_entity_types:       # verified in Phase 0
  - urn:entity:brand
venue_types:
  - id: cafe
    label: Cafés
    qloo_tags: [ "<tag id from Phase 0>" ]
    osm: { key: amenity, value: cafe }
  - id: bar
    label: Bars
    qloo_tags: [ "<tag id>" ]
    osm: { key: amenity, value: bar }
  - id: restaurant
    label: Restaurants
    qloo_tags: [ "<tag id>" ]
    osm: { key: amenity, value: restaurant }
  - id: deli
    label: Delis and specialty food shops
    qloo_tags: [ "<tag id>" ]
    osm: { key: shop, value: deli }
baseline_signal: none       # none | fixed_entities
baseline_entities: []       # used only if baseline_signal = fixed_entities
pitch_style:
  ask_examples: ["send a free sample", "a 10-minute tasting"]
  avoid: ["discount pressure", "health claims"]
```

`fashion.yaml` has the same shape with boutique and concept-store venue types.

## How it works

1. The intake (F01) classifies the brand into a pack or `unsupported`.
2. The engine reads venue types, tags and baseline settings from the pack. No category-specific code outside packs.
3. A pack with `status: secondary` is shown only if `PACK_FASHION_ENABLED=true`, which is set after Phase 0 proves Qloo returns boutiques in the demo city.
4. Unsupported businesses see Flow D.

## Phase 0 work for packs

- Discover Qloo tag ids for each venue type with `/v2/tags` searches and confirm that `filter.tags` returns those place types in the demo city. Record them in the pack and in `docs/qloo-contract.md`.
- Decide `baseline_signal` per pack based on the baseline experiment in `04-qloo-integration.md`.

## Tests

| What | How |
|---|---|
| Pack files validate against a schema at startup | Unit test |
| No category name appears in engine code outside `categories/` | Grep test in CI |
| Secondary pack hidden unless enabled | API test |
| Unsupported classification shows Flow D | API test |

Acceptance: CAT-01 to CAT-03.
