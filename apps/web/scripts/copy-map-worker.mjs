// MapLibre 6 loads its web worker from beside its own module file, which a bundled chunk is not. Serve the worker and
// the shared code it imports from public/maplibre (gitignored); runs after every install.
import { cpSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const dist = fileURLToPath(new URL(".", import.meta.resolve("maplibre-gl")));
const out = fileURLToPath(new URL("../public/maplibre/", import.meta.url));
mkdirSync(out, { recursive: true });
for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) cpSync(dist + f, out + f);
