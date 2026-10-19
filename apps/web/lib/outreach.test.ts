import { describe, expect, it, vi } from "vitest";

const { api } = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("./api", () => ({ api }));
import { cancelOutreach, sendAll, startOutreach, startingOutreach } from "./outreach";

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

describe("send all", () => {
  it("sends one by one, reports failures, and stops when Gmail wants permission again", async () => {
    const drafts = ["a", "b", "c", "d"].map((id) => ({ id, venue_name: `Venue ${id}` }));
    api.mockReset();
    api.mockImplementation((path: string) => {
      if (path.includes("/b/")) return Promise.reject({ code: "conflict", detail: "This contact is on your do-not-contact list." });
      if (path.includes("/c/")) return Promise.reject({ code: "gmail_reconnect" });
      return Promise.resolve({ id: path.split("/")[3], status: "sent" });
    });
    const steps: [number, string | null][] = [];
    const r = await sendAll(drafts, "ya29.t", (done, d) => steps.push([done, d?.id ?? null]));
    expect(r).toEqual({ sent: 1, failed: ["Venue b: This contact is on your do-not-contact list."], reconnect: true });
    expect(steps).toEqual([[1, "a"], [2, null]]); // d never tried: it waits for the next click
    expect(api).toHaveBeenCalledWith("/v1/drafts/a/send", { method: "POST", body: { google_access_token: "ya29.t" } });
    expect(api).toHaveBeenCalledTimes(3);
  });
});
