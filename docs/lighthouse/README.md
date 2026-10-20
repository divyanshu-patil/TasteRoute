# Lighthouse reports

Lighthouse 12.6.1, default mobile settings (simulated throttling), on a **local production build** (`next build && next start`, API on localhost with the sample run), 2026-10-20. The hosted demo is not deployed yet; rerun these against it before quoting hosted numbers.

| Page | Accessibility | Performance | Best practices |
|---|---|---|---|
| Landing `/` | 100 | 96 | 100 |
| Sample results `/runs/{id}` | 96 | 87 | 100 |
| Venue `/runs/{id}/venues/{venue}` | 100 | 79 | 100 |
| Outreach | 100 | 90 | 100 |
| Trace | 100 | 93 | 100 |
| Start `/start` | 100 | 92 | 100 |
| Evaluation `/evaluation` | 100 | 96 | 100 |

The one accessibility failure on results is `target-size`: numbered map pins that sit close together overlap (rank 8 is partly covered). Performance varies by about ±8 between runs on the same build (the venue page measured 89 and 79).

Each page has `<name>.report.html` (open in a browser) and `<name>.report.json`.
