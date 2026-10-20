-- QLO-11: a suggested visiting order for the top venues, grouped into walkable areas and ordered by Qloo's taste
-- heatmap (the brand signal's heatmap minus the mass-market one). {"areas": [...], "heat": [[lat, lon, lift]], ...}.
-- Never changes a score.
alter table runs add column route jsonb;
