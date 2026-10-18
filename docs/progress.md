# Progress

## Phase 0: Spikes — done 2026-10-19

| Spike | Result |
|---|---|
| S1 Qloo places in Brooklyn | Pass: 50/type (café, bar, restaurant, deli), 100% tagged, 82–100% with website |
| S2 Taste signal changes ranking | Pass: brand-vs-brand top-20 Jaccard 0.176 (café), 0.212 (bar); target vs baseline 0.08–0.21, Spearman −0.17 |
| S3 Resolution | Pass: comparables 9/9; small brands 2/7 self-resolve |
| S4 Explainability | Available on the same call; plus audience tag insights (1 call) |
| S5 Gemma 4 tool calling | Pass: 5/5 round trips on `gemma4:31b` (Ollama Cloud) |
| S6 Contacts | OSM match 30/50, OSM email 4/50; own-site email 3/12; Hunter blocked (no key) |

Go/no-go: **GO**, demo city Brooklyn. Contracts: `docs/qloo-contract.md`, `docs/llm-contract.md`.

## Budget used

| Service | Calls |
|---|---|
| Qloo | 43 live (36 × 200, 7 × 400 while learning `take` limit and shell quoting) |
| Ollama Cloud | ~20 (spike) |
| Nominatim / Overpass | 1 / 1 |
| Hunter | 0 (no key) |

## Blockers / needed from the user

- `HUNTER_API_KEY` (optional; contacts work without it, see D-08).
- Supabase `DATABASE_URL` (using local Postgres until then).
- Hosting accounts for the required public demo (web on Vercel, API on Render/Railway/Fly).
