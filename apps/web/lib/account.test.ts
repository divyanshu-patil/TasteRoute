import { beforeEach, describe, expect, it } from "vitest";
import { forgetGoogle, googleToken } from "./account";

describe("Google token for sending", () => {
  beforeEach(() => window.localStorage.clear());

  it("is used only while fresh, and a forgotten one stays expired", () => {
    expect(googleToken()).toBeNull();
    window.localStorage.setItem("tr_google", JSON.stringify({ token: "ya29.a", exp: Date.now() + 60_000 }));
    expect(googleToken()).toBe("ya29.a");
    forgetGoogle(); // Gmail said no: kept but marked expired, so Supabase's saved copy can't revive it
    expect(googleToken()).toBeNull();
    expect(JSON.parse(window.localStorage.getItem("tr_google")!).token).toBe("ya29.a");
  });
});
