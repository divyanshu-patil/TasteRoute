-- Photon (search-as-you-type place suggestions) joins the logged external services.
alter table external_calls drop constraint external_calls_service_check;
alter table external_calls add constraint external_calls_service_check
  check (service in ('website','nominatim','overpass','hunter','apollo','photon'));
