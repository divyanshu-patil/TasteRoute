# 00. Product brief

## One line

**Stockist Scout tells a brand which cafés, bars, restaurants and shops to pitch, which product to lead with at each, and why, based on what each venue's own customers like.**

## The problem

A small brand or a field sales rep faces thousands of possible accounts in a city. Lists of businesses and their emails are easy to get (Google Maps, Apollo, Hunter). What is hard is choosing **which accounts are a good fit**, and **what to say** so the pitch lands. Today this is done by guesswork, walking the streets, or paying a broker.

Fit for a consumer-facing business depends mostly on its customers: a café stocks what its guests like. No sales database knows that. Qloo does: it models what people who go to a place also like across food, drink, music, fashion, brands and more.

## Users (MVP)

| User | Situation | Decision |
|---|---|---|
| **Founder of a small food or drink brand** (coffee, spirits, beer, kombucha, snacks, sauces) | Needs the first 20–200 wholesale accounts | Which 30–50 venues to pitch first in a city, and with which message |
| **Field sales rep or small distributor** carrying several brands | Has a territory and a sales quota | Which accounts to visit this month and which product from the portfolio to lead with at each |

Secondary category (demo only if Phase 0 shows data coverage): **fashion and accessory labels pitching boutiques and concept stores.**

## What the user gets

1. A **ranked list of venues** in a chosen city, with a taste-fit score compared against a popularity baseline, so the list is not just "the busiest places".
2. For each venue, **which of the user's products fits best** and a plain reason taken from Qloo's explanation.
3. A **public business contact** for the venue where one exists (Hunter domain search on the venue's website, or the email listed on OpenStreetMap), with the source shown.
4. A **pitch email draft** per venue that cites the taste match, for the user to edit and approve.
5. **Export**: approved drafts as "open in email app" links and a CSV of the account list.
6. A **trace** of every Qloo and external call that produced each claim.

## Why Qloo is essential (the swap test)

| Without Qloo | With Qloo |
|---|---|
| "All 1,200 cafés in the city", sorted by rating or distance | "These 40 cafés, because their guests over-index on specialty coffee and natural wine" |
| Same product pitched everywhere | "Lead with product B at these 12 venues" |
| Generic email | Email that names the specific taste overlap |

If Qloo is switched off, the app must say it cannot rank venues and stop. This is tested (see `12-acceptance-criteria.md`, QLO-02).

## Value proposition

- **For a brand:** fewer wasted visits and emails; one new stockist usually pays for months of the tool.
- **For a rep:** a weekly route of high-fit accounts and the right product for each.

## What it is not

- Not a general lead-generation or cold-email tool for any business. If the user's prospects are not consumer-facing businesses that choose stock by customer taste, the app says Qloo cannot help.
- Not an email sender. Not a CRM. Not a prediction of sales.

## Success metrics

| Metric | Target for the hackathon demo |
|---|---|
| Qloo-on ranking judged better than Qloo-off in blind review | Qloo-on preferred in at least 7 of 10 venue pairs (see `15-evaluation.md`) |
| Venues with a usable reason | 100% of shown venues have a Qloo-derived reason |
| Venues with a found business contact | Reported honestly; target 40%+ in the demo city |
| Time from website to ranked list | Under 90 seconds on a warm cache |
| Drafts that cite only real evidence | 100% (grounding validator) |

## Positioning against existing tools

- **Explee, Apollo, Clay:** find companies and emails using company data. They cannot see what a venue's customers like.
- **Overproof (liquor):** ranks accounts by cocktail trends, competitor placements and venue type. Stockist Scout ranks by the taste of the venue's customers and works beyond liquor.
- **Qloo hackathon 2025 winners** (GeoTaste, Resonance AI, Zesty, Alloy): none pick accounts for a brand or match products to venues.
