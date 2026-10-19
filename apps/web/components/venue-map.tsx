"use client";

import "leaflet/dist/leaflet.css";
import type * as Leaflet from "leaflet";
import { useEffect, useRef } from "react";

export type Pin = { id: string; lat: number; lon: number; label: string; title: string; sub?: string; href?: string; on?: boolean; dot?: boolean; base?: boolean };
type Props = { pins: Pin[]; label: string; height?: number; bounds?: number[]; onPick?: (lat: number, lon: number) => void };

// Standard OSM tiles (no key; light use with attribution), desaturated in CSS to sit on the grey canvas.
// ponytail: fine at demo traffic; switch to a keyed or self-hosted tile service before real usage.
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** Leaflet map in the design system. `bounds` ([s, w, n, e]) frames an empty map, else it shows the world; `onPick` makes a click choose a point. */
export function VenueMap({ pins, label, height = 380, bounds, onPick }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const L = useRef<typeof Leaflet | null>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const layer = useRef<Leaflet.LayerGroup | null>(null);
  const latest = useRef(pins);
  const area = useRef(bounds);
  const pick = useRef(onPick);
  const fitted = useRef({ ids: "", where: "" });

  const draw = () => {
    const l = L.current, m = map.current, g = layer.current;
    if (!l || !m || !g) return;
    g.clearLayers();
    const pts = latest.current;
    const box = area.current?.length === 4 ? (area.current as [number, number, number, number]) : null;
    const boxLL: Leaflet.LatLngBoundsExpression | null = box && [[box[0], box[1]], [box[2], box[3]]];
    if (boxLL) l.rectangle(boxLL, { className: "map-area", interactive: false }).addTo(g); // the city being scouted
    for (const p of [...pts].reverse()) { // rank 1 drawn last, on top
      const size: [number, number] = p.dot ? [12, 12] : p.base ? [48, 28] : [30, 30];
      const cls = p.dot ? "pin-dot" : p.base ? "pin pin-base" : `pin${p.on ? " pin-on" : ""}`;
      const icon = l.divIcon({ className: "", html: `<span class="${cls}">${p.dot ? "" : esc(p.label)}</span>`, iconSize: size, iconAnchor: [size[0] / 2, size[1] / 2] });
      l.marker([p.lat, p.lon], { icon, title: p.title, alt: p.title, riseOnHover: true, zIndexOffset: p.dot ? 0 : p.base ? 3000 : p.on ? 2000 : 1000 })
        .bindPopup(`<strong>${esc(p.title)}</strong>${p.sub ? `<br><span class="mono">${esc(p.sub)}</span>` : ""}${p.href ? `<br><a href="${esc(p.href)}">Open venue →</a>` : ""}`)
        .addTo(g);
    }
    const ids = pts.map((p) => p.id).join(), where = `${box}|${el.current?.clientWidth}`;
    if (ids === fitted.current.ids && where === fitted.current.where) return; // selection changes recolour pins without moving the map
    const moved = where !== fitted.current.where; // a new city (or size) is framed whole
    fitted.current = { ids, where };
    m.invalidateSize();
    const focus = pts.some((p) => !p.dot) ? pts.filter((p) => !p.dot) : pts; // frame the numbered pins; dots may sit just outside
    if (boxLL && (moved || !focus.length)) m.fitBounds(boxLL);
    else if (focus.length > 1) m.fitBounds(focus.map((p) => [p.lat, p.lon] as [number, number]), { padding: [32, 32], maxZoom: 15 });
    else if (focus[0]) m.setView([focus[0].lat, focus[0].lon], Math.max(15, pick.current ? m.getZoom() || 0 : 0));
    else m.setView([20, 0], 2); // nothing to frame yet: the world
  };

  useEffect(() => {
    let alive = true;
    import("leaflet").then((mod) => {
      if (!alive || !el.current || map.current) return;
      L.current = mod;
      map.current = mod.map(el.current, { scrollWheelZoom: false });
      mod.tileLayer(TILES, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(map.current);
      layer.current = mod.layerGroup().addTo(map.current);
      map.current.on("click", (e: Leaflet.LeafletMouseEvent) => pick.current?.(e.latlng.lat, e.latlng.lng));
      draw();
    });
    const ro = new ResizeObserver(() => draw()); // refit once the card has its real size
    if (el.current) ro.observe(el.current);
    return () => {
      alive = false;
      ro.disconnect();
      map.current?.remove();
      map.current = null;
      fitted.current = { ids: "", where: "" };
    };
  }, []);

  useEffect(() => {
    latest.current = pins;
    area.current = bounds;
    pick.current = onPick;
    draw();
  }, [pins, bounds, onPick]);

  return <div ref={el} className={`map${onPick ? " map-pick" : ""}`} style={{ height }} role="region" aria-label={label} />;
}
