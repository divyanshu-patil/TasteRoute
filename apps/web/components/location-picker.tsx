"use client";

import { useCallback, useMemo, useRef } from "react";
import { ApiError, api, type S } from "../lib/api";
import { PlaceSearch } from "./place-search";
import { VenueMap, type Pin } from "./venue-map";

type City = S["CityHit"];
type Place = S["Place"];
type BaseProps = { city?: City | null; base: Place | null; onBase: (p: Place | null) => void; onError: (e: unknown) => void };

/** Where the brand itself is: search (inside the city when one is chosen) or click the map to drop a pin. */
export function BasePicker({ city, base, onBase, onError }: BaseProps) {
  const pinSeq = useRef(0);
  const inCity = city ? `&bbox=${city.bbox.join(",")}` : "";
  const findPlaces = (q: string) =>
    api<Place[]>(`/v1/places/search?q=${encodeURIComponent(q)}${inCity}`).catch((e: unknown) => {
      onError(e);
      throw e;
    });
  const suggestPlaces = (q: string) => api<Place[]>(`/v1/places/suggest?q=${encodeURIComponent(q)}${inCity}`);
  const dropPin = useCallback((lat: number, lon: number) => {
    const n = ++pinSeq.current; // a later click wins over a slow earlier lookup
    onBase({ label: "Dropped pin", detail: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon }); // until the address arrives
    api<Place>(`/v1/places/reverse?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}`)
      .then((p) => n === pinSeq.current && onBase(p))
      .catch(onError);
  }, [onBase, onError]);
  const pins = useMemo<Pin[]>(
    () => (base ? [{ id: `base:${base.lat},${base.lon}`, lat: base.lat, lon: base.lon, label: "You", title: base.label, sub: base.detail, base: true }] : []),
    [base],
  );

  return (
    <>
      <PlaceSearch id="base" label="Where is your business? (optional)" placeholder="Street address or business name"
        search={findPlaces} suggest={suggestPlaces} onPick={onBase}
        help={`Search ${city ? `inside ${city.label}` : "an address or business name"}, or click the map to drop a pin. You'll see how far each venue is from you; it never changes the ranking.`} />
      <VenueMap pins={pins} bounds={city?.bbox} onPick={dropPin} height={300}
        label={`Map${city ? ` of ${city.label}` : ""}. Click to place your business.`} />
      {base && (
        <div className="row between small" aria-live="polite">
          <span><strong>{base.label}</strong>{base.detail && <span className="muted"> · {base.detail}</span>}</span>
          <button className="link" onClick={() => onBase(null)}>Remove</button>
        </div>
      )}
    </>
  );
}

/** Wizard step 4: the city to scout, framed on the map, then the brand's own location. */
export function LocationPicker({ city, onCity, ...rest }: BaseProps & { city: City | null; onCity: (c: City | null) => void }) {
  const findCities = (q: string) => api<City[]>(`/v1/cities/search?q=${encodeURIComponent(q)}`);
  const fail = (e: unknown): never => {
    rest.onError(e);
    throw e;
  };
  // A typed suggestion has no area yet: one Nominatim lookup of its full name gives the bbox the run is limited to.
  const pick = (h: City | Place) => {
    if ("bbox" in h) return onCity(h);
    findCities(`${h.label}, ${h.detail ?? ""}`)
      .then((r) => (r[0] ? onCity(r[0]) : rest.onError(new ApiError(404, "not_found", "Couldn't find that city's area. Press Search instead.", ""))))
      .catch(rest.onError);
  };

  return (
    <>
      {city ? (
        <div className="banner banner-mint">
          <span className="dot" aria-hidden="true" />
          <div className="row between small" style={{ flex: 1 }}>
            <span><strong>Scouting {city.label}</strong>{city.detail && <> · {city.detail}</>}</span>
            <button className="link" onClick={() => onCity(null)}>Change city</button>
          </div>
        </div>
      ) : (
        <PlaceSearch<City | Place> id="city" label="City to scout" placeholder="Brooklyn" onPick={pick}
          search={(q) => findCities(q).catch(fail)}
          suggest={(q) => api<Place[]>(`/v1/places/suggest?kind=city&q=${encodeURIComponent(q)}`)}
          help="Qloo's place data is strongest in large cities. Brooklyn, NY is our tested demo city." />
      )}
      <BasePicker city={city} {...rest} />
    </>
  );
}
