# Lighthouse reports

Lighthouse 12.6.1, default mobile settings (simulated throttling), on a **local production build** (`next build && next start`, API on localhost, sample run `7892878f`), 2026-10-20. The hosted demo is not deployed yet; rerun these against it before quoting hosted numbers.

| Page | Accessibility | Performance | Best practices |
|---|---|---|---|
| Landing `/` | 100 | 96 | 100 |
| Sample results `/runs/{id}` (with the taste route and heatmap) | 100 | 87 | 100 |
| Venue `/runs/{id}/venues/{venue}` | 100 | 88 | 100 |
| Outreach | 100 | 88 | 100 |
| Trace | 100 | 89 | 100 |
| Start `/start` | 100 | 90 | 100 |
| Evaluation `/evaluation` | 100 | 96 | 100 |

Performance varies by about ±10 between runs of the same build: the results page measured 76 one run before the 87 above. An earlier pass on the previous sample run scored results 96 on accessibility (`target-size`: overlapping map pins) and found map pins whose names lacked their visible text, since fixed.

Each page has `<name>.report.html` (open in a browser) and `<name>.report.json`.
