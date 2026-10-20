-- EVL-06: an LLM's ranking of a run's venues from names, types and neighbourhoods only, shown next to Qloo's for
-- comparison. {"prompt_version": text, "ranks": {venue_id: rank}, "created_at": text}. Never changes a score.
alter table runs add column llm_ranking jsonb;
