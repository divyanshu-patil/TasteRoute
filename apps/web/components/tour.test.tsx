import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { Tour } from "./tour";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("tour=1"),
  usePathname: () => "/runs/x",
  useRouter: () => ({ replace }),
}));
beforeAll(() => { Element.prototype.scrollIntoView = () => {}; });

describe("Tour", () => {
  it("skips steps whose target is missing, outlines the current one, and closes on Esc", async () => {
    vi.useFakeTimers();
    render(
      <>
        <div data-tour="a">A</div>
        <div data-tour="c">C</div>
        <Tour ready steps={[{ target: "a", title: "First", body: "" }, { target: "b", title: "Hidden", body: "" }, { target: "c", title: "Last", body: "" }]}
          next={{ href: "/next?tour=1", label: "Go on" }} />
      </>,
    );
    await act(() => vi.advanceTimersByTimeAsync(200));
    expect(screen.getByText("TOUR · 01 / 02")).toBeTruthy();
    expect(screen.getByText("A").classList.contains("tour-target")).toBe(true);
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Last")).toBeTruthy();
    expect(screen.getByText("A").classList.contains("tour-target")).toBe(false);
    expect(screen.getByText("Go on →").getAttribute("href")).toBe("/next?tour=1");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(replace).toHaveBeenCalledWith("/runs/x", { scroll: false });
    vi.useRealTimers();
  });
});
