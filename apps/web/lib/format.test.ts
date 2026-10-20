import { describe, expect, it } from "vitest";
import { km, kmText, liftText, pct, venueTypeLabel } from "./format";

describe("format", () => {
  it("shows lift against a typical venue", () => {
    expect(liftText(0.234)).toBe("+23 vs typical");
    expect(liftText(0.001)).toBe("typical");
    expect(liftText(-0.4)).toBe("-40 vs typical");
    expect(liftText(0.234, true)).toBe("+23 vs mass-market taste");
  });
  it("measures straight-line distance in km", () => {
    const d = km({ lat: 40.7291, lon: -73.954 }, { lat: 40.7178, lon: -73.9576 }); // Greenpoint to Williamsburg, ~1.3 km
    expect(d).toBeGreaterThan(1.2);
    expect(d).toBeLessThan(1.4);
    expect(kmText(d)).toBe("1.3 km");
    expect(kmText(12.4)).toBe("12 km");
  });
  it("rounds scores to 0-100", () => {
    expect(pct(0.8916)).toBe(89);
  });
  it("labels venue types", () => {
    expect(venueTypeLabel("bar")).toBe("Bar");
  });
});
