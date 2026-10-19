import type { StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";
import { trimStyle } from "./map-style";

describe("trimStyle", () => {
  const style = {
    version: 8,
    sources: {},
    layers: [
      { id: "water", type: "fill", source: "openmaptiles", "source-layer": "water" },
      { id: "poi_r1", type: "symbol", source: "openmaptiles", "source-layer": "poi", minzoom: 15, filter: [">=", ["get", "rank"], 1] },
      { id: "poi_transit", type: "symbol", source: "openmaptiles", "source-layer": "poi" },
      { id: "building-3d", type: "fill-extrusion", source: "openmaptiles", "source-layer": "building" },
      { id: "highway-shield-us-interstate", type: "symbol", source: "openmaptiles", "source-layer": "transportation_name" },
      { id: "airport", type: "symbol", source: "openmaptiles", "source-layer": "aerodrome_label" },
    ],
  } as StyleSpecification;

  it("keeps the base map, drops transit, airports, 3D buildings and shields, and limits points of interest to food and sights", () => {
    const out = trimStyle(style);
    expect(out.layers.map((l) => l.id)).toEqual(["water", "poi_r1"]);
    const poi = out.layers[1] as { filter: unknown[]; minzoom: number };
    expect(poi.minzoom).toBe(13);
    expect(poi.filter[0]).toBe("all");
    expect(poi.filter[1]).toEqual([">=", ["get", "rank"], 1]); // the style's own rule still applies
    expect(JSON.stringify(poi.filter[2])).toContain('"restaurant"');
    expect(JSON.stringify(poi.filter[2])).not.toContain('"bus"');
  });
});
