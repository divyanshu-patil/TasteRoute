import { describe, expect, it } from "vitest";
import { liftText, pct, venueTypeLabel } from "./format";

describe("format", () => {
  it("shows lift against a typical venue", () => {
    expect(liftText(0.234)).toBe("+23 vs typical");
    expect(liftText(0.001)).toBe("typical");
    expect(liftText(-0.4)).toBe("-40 vs typical");
  });
  it("rounds scores to 0-100", () => {
    expect(pct(0.8916)).toBe(89);
  });
  it("labels venue types", () => {
    expect(venueTypeLabel("bar")).toBe("Bar");
  });
});
