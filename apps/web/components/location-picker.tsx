"use client";

import { useCallback, useMemo, useRef } from "react";
import { api, type S } from "../lib/api";
import { PlaceSearch } from "./place-search";
import { VenueMap, type Pin } from "./venue-map";

type City = S["CityHit"];
type Place = S["Place"];

/** Wizard step 4: the city to scout, then optionally where the brand itself is (search or a pin on the map). */
export function LocationPicker({ city, base, onCity, onBase, onError }: {
  city: City | null;
  base: Place | null;
  onCity: (c: City | null) => void;
  onBase: (p: Place | null) => void;
  onError: (e: unknown) => void;
}) {
  const pinSeq = useRef(0);
  const fail = (e: unknown): never => {
    onError(e);
    throw e;
  };
  const findCities = (q: string) => api<City[]>(`/v1/cities/search?q=${encodeURIComponent(q)}`).catch(fail);
  const findPlaces = (q: string) =>
    api<Place[]>(`/v1/places/search?q=${encodeURIComponent(q)}&bbox=${city?.bbox.join(",") ?? ""}`).catch(fail);
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
            {city ? (
              <div className="banner banner-mint">
                <span className="dot" aria-hidden="true" />
                <div className="row between small" style={{ flex: 1 }}>
                  <span><strong>Scouting {city.label}</strong>{city.detail && <> · {city.detail}</>}</span>
                  <button className="link" onClick={() => { onCity(null); onBase(null); }}>Change city</button>
                </div>
              </div>
            ) : (
              <PlaceSearch id="city" label="City to scout" placeholder="Brooklyn" search={findCities} onPick={onCity}
                help="Qloo's place data is strongest in large cities. Brooklyn, NY is our tested demo city." />
            )}
            {city && (
              <>
                <PlaceSearch id="base" label="Where is your business? (optional)" placeholder="Street address or business name"
                  search={findPlaces} onPick={onBase}
                  help={`Search inside ${city.label}, or click the map to drop a pin. You'll see how far each venue is from you; the ranking still covers the whole city.`} />
                <VenueMap pins={pins} bounds={city.bbox} onPick={dropPin} height={300}
                  label={`Map of ${city.label}. Click to place your business.`} />
                {base && (
                  <div className="row between small" aria-live="polite">
                    <span><strong>{base.label}</strong>{base.detail && <span className="muted"> · {base.detail}</span>}</span>
                    <button className="link" onClick={() => onBase(null)}>Remove</button>
                  </div>
                )}
              </>
            )}
    </>
  );
}
