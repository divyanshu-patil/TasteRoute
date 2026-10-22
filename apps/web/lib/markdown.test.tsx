import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./markdown";

describe("Markdown", () => {
  it("renders lists, bold, code and safe links only", () => {
    const { container } = render(
      <Markdown text={"Top picks:\n\n1. **#1 Bar One**: fit 87\n2. #2 Cafe Two\n- `x` and *y*\n\n[venue](/runs/a) [bad](javascript:alert(1))"} />,
    );
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelector("ol strong")?.textContent).toBe("#1 Bar One");
    expect(container.querySelector("ul code")?.textContent).toBe("x");
    expect(container.querySelector("ul em")?.textContent).toBe("y");
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(1);
    expect(links[0]?.getAttribute("href")).toBe("/runs/a");
    expect(container.textContent).toContain("bad");
    expect(container.innerHTML).not.toContain("javascript");
  });
});
