-- Score plan C1/C2 (RNK-07, FIT-04): lift is measured against mass-market taste at the same venues, so baseline_pct now
-- holds the generic-signal percentile; each venue's own Qloo popularity percentile is kept for display. Each product's
-- raw Qloo affinity per venue is stored so the best product can be chosen by standardised affinity.
alter table venue_scores add column popularity_pct numeric(5,4);
alter table venue_product_fit add column affinity double precision;
