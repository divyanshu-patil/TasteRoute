import type { ExpressionSpecification, FilterSpecification, LayerSpecification, StyleSpecification } from "maplibre-gl";

// OpenFreeMap: OpenStreetMap vector tiles, no key and no usage limits, attribution comes with the tiles.
export const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

// Points of interest worth seeing on a TasteRoute map: food and drink, plus famous sights to get your bearings.
// OpenMapTiles groups some of these under a class (grocery, beer, alcohol_shop) and keeps the OSM tag as subclass.
const FOOD = ["restaurant", "fast_food", "food_court", "cafe", "bar", "pub", "beer", "biergarten", "ice_cream", "bakery",
  "pastry", "confectionery", "chocolate", "coffee", "tea", "deli", "delicatessen", "butcher", "cheese", "seafood",
  "greengrocer", "grocery", "supermarket", "marketplace", "alcohol_shop", "alcohol", "beverages", "wine"];
const SIGHTS = ["attraction", "museum", "castle", "monument", "stadium", "zoo"];
// Everything else that competes with the venue pins.
const NOISE = /^(poi_transit|airport|building-3d|road_one_way_arrow.*|highway-shield-.*|road_shield_us)$/;

const tagged = (values: string[]): ExpressionSpecification =>
  ["any", ["in", ["get", "class"], ["literal", values]], ["in", ["get", "subclass"], ["literal", values]]];
const KEEP: ExpressionSpecification = ["any", tagged(FOOD), ["all", tagged(SIGHTS), ["<", ["get", "rank"], 7]]]; // rank < 7: only well-known sights

/** The Liberty style with only food, drink and famous sights left among the points of interest, shown two zoom levels sooner. */
export function trimStyle(style: StyleSpecification): StyleSpecification {
  const layers = style.layers
    .filter((l) => !NOISE.test(l.id))
    .map((l): LayerSpecification => {
      if (l.type !== "symbol" || l["source-layer"] !== "poi") return l;
      const filter: FilterSpecification = l.filter ? ["all", l.filter as ExpressionSpecification, KEEP] : KEEP; // Liberty's filters are expressions
      return { ...l, filter, minzoom: (l.minzoom ?? 15) - 2 };
    });
  return { ...style, layers };
}

// If OpenFreeMap is unreachable, plain OSM raster tiles keep the pins on a map.
export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

let style: Promise<StyleSpecification> | undefined;
/** Fetched once per page load and shared by every map. */
export const mapStyle = () =>
  (style ??= fetch(STYLE_URL)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`style ${r.status}`))))
    .then(trimStyle)
    .catch(() => {
      style = undefined; // try again next time
      return FALLBACK_STYLE;
    }));
