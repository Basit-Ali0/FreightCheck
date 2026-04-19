import { describe, expect, it } from "vitest";

import { formatAbsolute, formatElapsed, formatRelative } from "@/lib/time";

describe("time helpers", () => {
  it("formatAbsolute returns a non-empty string for valid ISO", () => {
    const s = formatAbsolute("2020-06-01T12:00:00.000Z");
    expect(s.length).toBeGreaterThan(4);
  });

  it("formatAbsolute falls back on invalid input", () => {
    expect(formatAbsolute("not-a-date")).toBe("not-a-date");
  });

  it("formatRelative returns a label for a past timestamp", () => {
    const past = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(formatRelative(past).length).toBeGreaterThan(0);
  });

  it("formatElapsed formats ms and seconds", () => {
    expect(formatElapsed(500)).toContain("ms");
    expect(formatElapsed(3000)).toContain("3");
  });

  it("formatElapsed formats minutes when over 60s", () => {
    expect(formatElapsed(125_000)).toMatch(/2m/);
  });

  it("formatRelative uses hour and day branches with fixed clock", () => {
    const now = 1_700_000_000_000;
    const hoursAgo = new Date(now - 5 * 3600_000).toISOString();
    expect(formatRelative(hoursAgo, now).length).toBeGreaterThan(0);
    const daysAgo = new Date(now - 3 * 24 * 3600_000).toISOString();
    expect(formatRelative(daysAgo, now).length).toBeGreaterThan(0);
    const monthsAgo = new Date(now - 40 * 24 * 3600_000).toISOString();
    expect(formatRelative(monthsAgo, now).length).toBeGreaterThan(0);
  });
});
