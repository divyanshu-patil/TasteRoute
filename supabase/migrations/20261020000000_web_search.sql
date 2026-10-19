-- Ollama web search: the last place TasteRoute looks for a venue's published email (F06).
alter table external_calls drop constraint external_calls_service_check;
alter table external_calls add constraint external_calls_service_check
  check (service in ('website','nominatim','overpass','hunter','apollo','photon','web_search'));
alter table contacts drop constraint contacts_source_check;
alter table contacts add constraint contacts_source_check
  check (source in ('hunter','osm','qloo','apollo','website','web'));
