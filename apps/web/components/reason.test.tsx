import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReasonText } from "./reason";
import { ConfidenceBadge } from "./ui";

describe("ReasonText", () => {
  it("turns source markers into labelled chips", () => {
    render(<ReasonText text="Guests here over-index on espresso bar (Qloo). Lead with Cold Brew (our inference)." />);
    expect(screen.getByText("Qloo")).toBeTruthy();
    expect(screen.getByText("Our inference")).toBeTruthy();
    expect(screen.queryByText(/\(Qloo\)/)).toBeNull();
    expect(screen.getByText(/espresso bar\./)).toBeTruthy();
  });
});

describe("ConfidenceBadge", () => {
  it("names the level in text, not only colour", () => {
    render(<ConfidenceBadge level="high" />);
    expect(screen.getByText("high")).toBeTruthy();
    expect(screen.getByRole("tooltip").textContent).toContain("Top 20%");
  });
});
