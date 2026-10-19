import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

// UI-05: honest copy. Taste fit is never sold as purchase intent.
it("UI copy never says 'will buy' or 'demand'", () => {
  const files = ["app", "components", "lib"].flatMap((d) =>
    readdirSync(d, { recursive: true, encoding: "utf8" }).filter((f) => /\.tsx?$/.test(f) && !f.includes(".test.")).map((f) => join(d, f)),
  );
  const hits = files.filter((f) => /will buy|demand/i.test(readFileSync(f, "utf8")));
  expect(files.length).toBeGreaterThan(10);
  expect(hits).toEqual([]);
});
