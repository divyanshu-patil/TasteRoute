# 01. Scope

## MVP (must ship by Oct 29, 2026)

| ID | Capability | Feature file |
|---|---|---|
| S1 | Brand intake from a website URL or typed description, with an editable brand profile and up to 5 products | `features/F01-brand-intake.md` |
| S2 | Resolve each product to Qloo entities (the product itself or comparable known brands) | `features/F02-entity-resolution.md` |
| S3 | Rank venues in one city by taste fit with lift over a popularity baseline | `features/F03-venue-ranking.md` |
| S4 | Pick the best product per venue | `features/F04-product-fit.md` |
| S5 | Evidence: Qloo explanation, scores and sources per venue | `features/F05-evidence.md` |
| S6 | Business contact discovery (OpenStreetMap tags, Hunter domain search) | `features/F06-contacts.md` |
| S7 | Pitch drafting, editing and approval | `features/F07-pitch-drafts.md` |
| S8 | Export (mailto links, CSV) and opt-out suppression list | `features/F08-export-and-suppression.md` |
| S9 | Agent orchestration with live progress and a full call trace | `features/F09-agent-orchestration.md` |
| S10 | Demo mode, caching and budget guard | `features/F10-demo-and-budget.md` |
| S11 | Category packs: Food and drink (full); Fashion (secondary, if Phase 0 proves coverage) | `features/F11-category-packs.md` |

## Category support

| Category | Seller | Prospects | MVP status |
|---|---|---|---|
| Food and drink | Coffee, spirits, beer, wine, kombucha, snacks, sauces | Cafés, bars, restaurants, delis, specialty food shops | **Full** |
| Fashion and accessories | Labels, jewellery, eyewear | Boutiques, concept stores | **Secondary demo** only if Phase 0 shows Qloo returns these places in the demo city |
| Books | Authors, small publishers | Bookstores, libraries | Roadmap |
| Music and events | Artists, DJs, promoters | Venues, hotels, bars | Roadmap |
| Not supported | Software, cleaning, logistics, professional services | Any | The app explains that Qloo cannot rank these prospects |

## Out of scope for the hackathon

- Sending email from the app, sequences, follow-ups, reply handling, meeting booking.
- User accounts and teams. The MVP uses an anonymous workspace per browser (see `03-architecture.md`).
- Payments, billing, subscriptions.
- Multiple cities per run (one city per run; the user can start another run).
- Mobile apps.
- Contacts for named individuals beyond what Hunter returns for the venue domain. No personal or consumer data.
- Apollo integration is optional and **off by default** (see `09-external-services.md`).
- Running any model locally.

## Constraints

- Qloo hackathon API: 5 requests per second, 10,000 calls per month.
- Hunter free plan: 50 credits per month (domain search uses credits). Plan for a paid month if the demo needs more, or use cached demo data.
- Nominatim: at most 1 request per second, identifying User-Agent, cache results.
- Overpass: no parallel queries, cache results, back off on 429.
- Judges must be able to test the app free and without restriction (hackathon rule). The demo must therefore work without spending live credits per visitor (see F10).
- Repository must be public with an open-source license file (hackathon rule).

## Definition of done

Every criterion in `12-acceptance-criteria.md` marked "MVP" passes, the pre-submit checklist in `14-checks.md` is complete, and the Qloo-on versus Qloo-off evaluation in `15-evaluation.md` has been run and reported honestly.
