import { describe, expect, it, vi } from "vitest";

const { api } = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("./api", () => ({ api }));
import { cancelOutreach, startOutreach, startingOutreach } from "./outreach";

describe("outreach start and cancel", () => {
  it("shares the start with the outreach page; cancel aborts it and stops the API's work", async () => {
    let signal: AbortSignal | undefined;
    api.mockImplementation((path: string, init: { signal?: AbortSignal }) => {
      if (!path.endsWith("/contacts")) return Promise.resolve({ status: "scouted" });
      signal = init.signal; // a start the API hasn't answered yet
      return new Promise((_, fail) => init.signal?.addEventListener("abort", () => fail(new DOMException("aborted", "AbortError"))));
    });
    startOutreach("r1", ["v1"]);
    expect(api).toHaveBeenCalledWith("/v1/runs/r1/contacts", expect.objectContaining({ method: "POST", body: { venue_ids: ["v1"] } }));
    const start = startingOutreach("r1");
    expect(start).not.toBeNull();
    expect(startingOutreach("r2")).toBeNull();

    await cancelOutreach("r1");
    expect(signal?.aborted).toBe(true);
    expect(api).toHaveBeenLastCalledWith("/v1/runs/r1/cancel", { method: "POST" });
    await expect(start).rejects.toThrow("aborted");
    await vi.waitFor(() => expect(startingOutreach("r1")).toBeNull());
  });
});
