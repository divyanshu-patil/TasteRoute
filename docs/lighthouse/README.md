# Lighthouse reports

Lighthouse 12.6.1, default mobile settings (simulated throttling), on the **hosted demo** (https://taste-route.vercel.app, API on Render, sample run `7892878f`), 2026-10-20.

| Page | Accessibility | Performance | Best practices | Largest paint |
|---|---|---|---|---|
| Landing `/` | 100 | 97 | 100 | 2.4 s |
| Sample results `/runs/{id}` (with the taste route and heatmap) | 100 | 65 | 100 | 3.6 s |
| Venue `/runs/{id}/venues/{venue}` | 100 | 88 | 100 | 3.6 s |
| Outreach | 100 | 91 | 100 | 3.5 s |
| Trace | 100 | 90 | 100 | 3.6 s |
| Start `/start` | 100 | 94 | 100 | 2.6 s |
| Evaluation `/evaluation` | 100 | 98 | 100 | 2.4 s |

The results page is slowest: starting the map (MapLibre, 60 venues and the heatmap) blocks the main thread for about 1.1 s. A local production build measured it at 76 and 87 on two runs, so performance varies by about ±10 between runs. An earlier pass on the previous sample run scored results 96 on accessibility (`target-size`: overlapping map pins) and found map pins whose names lacked their visible text, since fixed.

Each page has `<name>.report.html` (open in a browser) and `<name>.report.json`.
