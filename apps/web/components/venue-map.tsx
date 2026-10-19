"use client";

import "leaflet/dist/leaflet.css";
import type * as Leaflet from "leaflet";
import { useEffect, useRef } from "react";

export type Pin = { id: string; lat: number; lon: number; label: string; title: string; sub?: string; href?: string; on?: boolean; dot?: boolean };

// Standard OSM tiles (no key; light use with attribution), desaturated in CSS to sit on the grey canvas.
// ponytail: fine at demo traffic; switch to a keyed or self-hosted tile service before real usage.
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export function VenueMap({ pins, label, height = 380 }: { pins: Pin[]; label: string; height?: number }) {
  const el = useRef<HTMLDivElement>(null);
  const L = useRef<typeof Leaflet | null>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const layer = useRef<Leaflet.LayerGroup | null>(null);
  const latest = useRef(pins);
  const fitted = useRef("");

  const draw = () => {
    const l = L.current, m = map.current, g = layer.current;
    if (!l || !m || !g) return;
    g.clearLayers();
    const pts = latest.current;
    for (const p of [...pts].reverse()) { // rank 1 drawn last, on top
      const size = p.dot ? 12 : 30;
      const html = p.dot ? `<span class="pin-dot"></span>` : `<span class="pin${p.on ? " pin-on" : ""}">${esc(p.label)}</span>`;
      const icon = l.divIcon({ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
      l.marker([p.lat, p.lon], { icon, title: p.title, alt: p.title, riseOnHover: true, zIndexOffset: p.dot ? 0 : p.on ? 2000 : 1000 })
        .bindPopup(`<strong>${esc(p.title)}</strong>${p.sub ? `<br><span class="mono">${esc(p.sub)}</span>` : ""}${p.href ? `<br><a href="${esc(p.href)}">Open venue →</a>` : ""}`)
        .addTo(g);
    }
    const key = `${pts.map((p) => p.id).join()}|${el.current?.clientWidth}`;
    if (key === fitted.current) return; // selection changes recolour pins without moving the map
    fitted.current = key;
    m.invalidateSize();
    const focus = pts.some((p) => !p.dot) ? pts.filter((p) => !p.dot) : pts; // frame the numbered pins; dots may sit just outside
    if (focus.length > 1) m.fitBounds(focus.map((p) => [p.lat, p.lon] as [number, number]), { padding: [32, 32], maxZoom: 15 });
    else if (focus[0]) m.setView([focus[0].lat, focus[0].lon], 15);
  };

  useEffect(() => {
    let alive = true;
    import("leaflet").then((mod) => {
      if (!alive || !el.current || map.current) return;
      L.current = mod;
      map.current = mod.map(el.current, { scrollWheelZoom: false });
      mod.tileLayer(TILES, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(map.current);
      layer.current = mod.layerGroup().addTo(map.current);
      draw();
    });
    const ro = new ResizeObserver(() => draw()); // refit once the card has its real size
    if (el.current) ro.observe(el.current);
    return () => {
      alive = false;
      ro.disconnect();
      map.current?.remove();
      map.current = null;
      fitted.current = "";
    };
  }, []);

  useEffect(() => {
    latest.current = pins;
    draw();
  }, [pins]);

  return <div ref={el} className="map" style={{ height }} role="region" aria-label={label} />;
}
