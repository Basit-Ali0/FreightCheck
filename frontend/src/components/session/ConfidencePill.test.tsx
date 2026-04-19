import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ConfidencePill,
  confidenceBand,
  confidenceRowHighlightClass,
} from "@/components/session/ConfidencePill";

describe("confidenceRowHighlightClass", () => {
  it("emphasizes very low and sub-0.9 bands", () => {
    expect(confidenceRowHighlightClass(0.4)).toContain("ring-2");
    expect(confidenceRowHighlightClass(0.8)).toContain("ring-1");
    expect(confidenceRowHighlightClass(0.95)).toBe("");
  });
});

describe("confidenceBand", () => {
  it("maps four bands", () => {
    expect(confidenceBand(0.95)).toBe("high");
    expect(confidenceBand(0.8)).toBe("medium");
    expect(confidenceBand(0.55)).toBe("low");
    expect(confidenceBand(0.2)).toBe("very_low");
  });
});

describe("ConfidencePill", () => {
  it("exposes rationale in title tooltip", () => {
    render(<ConfidencePill confidence={0.92} rationale="Matches B/L header." />);
    const el = screen.getByText("92%");
    expect(el).toHaveAttribute(
      "title",
      expect.stringContaining("High (≥ 0.90) — Matches B/L header."),
    );
  });

  it("uses default rationale text when null", () => {
    render(<ConfidencePill confidence={0.4} rationale={null} />);
    const el = screen.getByText("40%");
    expect(el.getAttribute("title")).toContain("Very low (< 0.50)");
    expect(el.getAttribute("title")).toContain("No rationale recorded.");
  });
});
