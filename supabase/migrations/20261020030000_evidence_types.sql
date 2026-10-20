-- Score plan C2/E (FIT-04, QLO-09): the best product comes from Qloo per-product calls, so it is Qloo evidence, not an
-- inference; cross-domain taste (music, film, books) is Qloo evidence too.
alter table venue_evidence drop constraint venue_evidence_type_check;
alter table venue_evidence add constraint venue_evidence_type_check check (type in (
  'qloo_affinity','qloo_explanation','qloo_tag_overlap','qloo_venue_profile','qloo_product_fit','qloo_cross_domain',
  'osm_fact','contact_source','inference'));
