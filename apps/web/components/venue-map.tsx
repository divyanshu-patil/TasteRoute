"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import type * as ML from "maplibre-gl";
import { useEffect, useId, useRef } from "react";
import { mapStyle } from "../lib/map-style";

export type Pin = { id: string; lat: number; lon: number; label: string; title: string; sub?: string; href?: string; on?: boolean; dot?: boolean; base?: boolean };
type Props = { pins: Pin[]; label: string; height?: number; bounds?: number[]; onPick?: (lat: number, lon: number) => void };
type Box = [number, number, number, number]; // [s, w, n, e]

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** MapLibre map in the design system. `bounds` ([s, w, n, e]) is outlined and framed, else it shows the world; `onPick` makes a click choose a point. */
export function VenueMap({ pins, label, height = 380, bounds, onPick }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const after = `after-map-${useId().replace(/:/g, "")}`;
  const lib = useRef<typeof ML | null>(null);
  const map = useRef<ML.Map | null>(null);
  const markers = useRef<ML.Marker[]>([]);
  const ready = useRef(false); // style loaded, so the area outline can be added
  const latest = useRef(pins);
  const area = useRef(bounds);
  const pick = useRef(onPick);
  const fitted = useRef({ ids: "", where: "" });

  const outline = (m: ML.Map, box: Box | null) => {
    if (!ready.current || !el.current) return;
    const [s, w, n, e] = box ?? [0, 0, 0, 0];
    const ring = [[w, s], [e, s], [e, n], [w, n], [w, s]];
    const data = {
      type: "FeatureCollection",
      features: box ? [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } }] : [],
    } as Parameters<ML.GeoJSONSource["setData"]>[0];
    const src = m.getSource<ML.GeoJSONSource>("area");
    if (src) return void src.setData(data);
    const css = getComputedStyle(el.current);
    m.addSource("area", { type: "geojson", data });
    m.addLayer({ id: "area-fill", type: "fill", source: "area", paint: { "fill-color": css.getPropertyValue("--mint").trim(), "fill-opacity": 0.18 } });
    m.addLayer({ id: "area-line", type: "line", source: "area", paint: { "line-color": css.getPropertyValue("--black").trim(), "line-width": 1.5, "line-dasharray": [3, 3] } });
  };

  const draw = () => {
    const ml = lib.current, m = map.current;
    if (!ml || !m) return;
    const pts = latest.current;
    const box = area.current?.length === 4 ? (area.current as Box) : null;
    outline(m, box);
    for (const mk of markers.current) mk.remove();
    markers.current = pts.map((p, i) => { // added in list order, so Tab follows the rank; stacking puts rank 1 on top
      const node = document.createElement("div");
      node.className = p.dot ? "pin-dot" : p.base ? "pin pin-base" : `pin${p.on ? " pin-on" : ""}`;
      node.textContent = p.dot ? "" : p.label;
      node.title = p.title;
      node.style.zIndex = String(p.dot ? 1 : p.base ? 3000 : (p.on ? 2000 : 1000) - i);
      const popup = new ml.Popup({ offset: 18, maxWidth: "280px" })
        .setHTML(`<strong>${esc(p.title)}</strong>${p.sub ? `<br><span class="mono">${esc(p.sub)}</span>` : ""}${p.href ? `<br><a href="${esc(p.href)}">Open venue →</a>` : ""}`);
      const mk = new ml.Marker({ element: node }).setLngLat([p.lon, p.lat]).setPopup(popup).addTo(m); // Enter or Space opens it
      node.setAttribute("role", "button");
      node.setAttribute("aria-label", p.dot || p.title.startsWith(p.label) ? p.title : `${p.label}: ${p.title}`); // the name includes the visible text
      if (p.dot) node.setAttribute("tabindex", "-1"); // venues below the top 10 are in the table; keyboard users skip them here
      return mk;
    });
    const ids = pts.map((p) => p.id).join(), where = `${box}|${el.current?.clientWidth}`;
    if (ids === fitted.current.ids && where === fitted.current.where) return; // selection changes recolour pins without moving the map
    const moved = where !== fitted.current.where; // a new city (or size) is framed whole
    fitted.current = { ids, where };
    m.resize();
    const focus = pts.some((p) => !p.dot) ? pts.filter((p) => !p.dot) : pts; // frame the numbered pins; dots may sit just outside
    if (box && (moved || !focus.length)) m.fitBounds([[box[1], box[0]], [box[3], box[2]]], { padding: 16, animate: false });
    else if (focus.length > 1) {
      const b = new ml.LngLatBounds();
      for (const p of focus) b.extend([p.lon, p.lat]);
      m.fitBounds(b, { padding: 40, maxZoom: 15, animate: false });
    } else if (focus[0]) m.jumpTo({ center: [focus[0].lon, focus[0].lat], zoom: Math.max(15, pick.current ? m.getZoom() : 0) });
    else m.jumpTo({ center: [0, 20], zoom: 1 }); // nothing to frame yet: the world
  };

  useEffect(() => {
    let alive = true;
    Promise.all([import("maplibre-gl"), mapStyle()]).then(([ml, style]) => {
      if (!alive || !el.current || map.current) return;
      ml.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs"); // copied into public/ by scripts/copy-map-worker.mjs
      lib.current = ml;
      const m = new ml.Map({
        container: el.current, style, center: [0, 20], zoom: 1,
        scrollZoom: false, dragRotate: false, pitchWithRotate: false, touchPitch: false, attributionControl: { compact: false },
      });
      m.touchZoomRotate.disableRotation();
      m.keyboard.disableRotation();
      m.addControl(new ml.NavigationControl({ showCompass: false }), "top-left");
      m.on("click", (e) => {
        if ((e.originalEvent.target as Element).closest(".maplibregl-marker")) return; // a pin: its popup, not a new point
        pick.current?.(e.lngLat.lat, e.lngLat.lng);
      });
      m.on("load", () => {
        ready.current = true;
        draw();
      });
      map.current = m;
      draw();
    });
    const ro = new ResizeObserver(() => draw()); // refit once the card has its real size
    if (el.current) ro.observe(el.current);
    return () => {
      alive = false;
      ro.disconnect();
      map.current?.remove();
      map.current = null;
      markers.current = [];
      ready.current = false;
      fitted.current = { ids: "", where: "" };
    };
  }, []);

  useEffect(() => {
    latest.current = pins;
    area.current = bounds;
    pick.current = onPick;
    draw();
  }, [pins, bounds, onPick]);

  return (
    <div style={{ position: "relative" }}>
      <a className="skip-map" href={`#${after}`}>Skip map</a>
      <div ref={el} className={`map${onPick ? " map-pick" : ""}`} style={{ height }} role="region" aria-label={label} />
      <span id={after} tabIndex={-1} />
    </div>
  );
}
