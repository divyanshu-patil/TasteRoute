import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PlaceSearch } from "./place-search";

describe("PlaceSearch", () => {
  it("searches only on submit, lists plain-English suggestions and picks one", async () => {
    const hit = { label: "St. Agrestis", detail: "Greenpoint, Brooklyn, New York" };
    const search = vi.fn().mockResolvedValue([hit]);
    const onPick = vi.fn();
    render(<PlaceSearch id="b" label="Where is your business?" placeholder="Street" search={search} onPick={onPick} />);
    const input = screen.getByLabelText("Where is your business?");
    fireEvent.change(input, { target: { value: "  St. Agrestis " } });
    expect(search).not.toHaveBeenCalled(); // no autocomplete
    await act(async () => { fireEvent.submit(input.closest("form") as HTMLFormElement); });
    expect(search).toHaveBeenCalledWith("St. Agrestis");
    expect(screen.getByText("Greenpoint, Brooklyn, New York")).toBeTruthy();
    fireEvent.click(screen.getByText("St. Agrestis"));
    expect(onPick).toHaveBeenCalledWith(hit);
    expect(screen.queryByText("Greenpoint, Brooklyn, New York")).toBeNull();
  });

  it("says when nothing matches and closes on Escape", async () => {
    render(<PlaceSearch id="c" label="City" placeholder="Brooklyn" search={vi.fn().mockResolvedValue([])} onPick={vi.fn()} />);
    const input = screen.getByLabelText("City");
    fireEvent.change(input, { target: { value: "Atlantis" } });
    await act(async () => { fireEvent.submit(input.closest("form") as HTMLFormElement); });
    expect(screen.getByText(/No matches/)).toBeTruthy();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByText(/No matches/)).toBeNull();
  });

  it("suggests while typing after a pause, and only the latest text counts", async () => {
    vi.useFakeTimers();
    try {
      const suggest = vi.fn((q: string) => Promise.resolve([{ label: `${q} Street`, detail: "Greenpoint" }]));
      const search = vi.fn();
      render(<PlaceSearch id="t" label="Business" placeholder="Street" search={search} suggest={suggest} onPick={vi.fn()} />);
      const input = screen.getByLabelText("Business");
      fireEvent.change(input, { target: { value: "Fr" } });
      fireEvent.change(input, { target: { value: "Fran" } });
      fireEvent.change(input, { target: { value: "Frank" } });
      await act(async () => { vi.advanceTimersByTime(349); });
      expect(suggest).not.toHaveBeenCalled();
      await act(async () => { vi.advanceTimersByTime(1); });
      expect(suggest).toHaveBeenCalledTimes(1);
      expect(suggest).toHaveBeenCalledWith("Frank");
      expect(screen.getByText("Frank Street")).toBeTruthy();
      expect(search).not.toHaveBeenCalled(); // the full search waits for Enter
    } finally {
      vi.useRealTimers();
    }
  });
});
