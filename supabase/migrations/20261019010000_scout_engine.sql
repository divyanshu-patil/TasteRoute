-- Scout engine additions (D-05, D-06, D-13).
-- products.entities: user-confirmed Qloo entities [{entity_id, name, type, role, similarity, source_call_id}]
alter table products add column entities jsonb;

-- Venue crowd profile from Qloo place data (customer tags, demographics text).
alter table venue_evidence drop constraint venue_evidence_type_check;
alter table venue_evidence add constraint venue_evidence_type_check check (type in
  ('qloo_affinity','qloo_explanation','qloo_tag_overlap','qloo_venue_profile','osm_fact','contact_source','inference'));

-- Template reason (F05) stored with the score so every list read is one query.
alter table venue_scores add column reason text;

-- Evidence ids cited by drafts are checked against this index.
create index venue_evidence_run_idx on venue_evidence(run_id, id);
