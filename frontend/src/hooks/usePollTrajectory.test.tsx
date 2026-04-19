import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as sessionsApi from "@/api/sessions";
import { usePollTrajectory } from "@/hooks/usePollSession";
import type { TrajectoryResponse } from "@/types";

const baseTraj = (over: Partial<TrajectoryResponse> = {}): TrajectoryResponse => ({
  session_id: "sid",
  status: "processing",
  iteration_count: 0,
  planner_decisions: [],
  tool_calls: [],
  tokens_used: 0,
  elapsed_ms: 0,
  ...over,
});

describe("usePollTrajectory", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns null when disabled", () => {
    const { result } = renderHook(() => usePollTrajectory("sid", { enabled: false }));
    expect(result.current.trajectory).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("fetches trajectory when enabled", async () => {
    vi.spyOn(sessionsApi, "getTrajectory").mockResolvedValue(baseTraj());
    const { result } = renderHook(() =>
      usePollTrajectory("sid", { enabled: true, pollIntervalMs: 15 }),
    );
    await waitFor(() => expect(result.current.trajectory).not.toBeNull());
    expect(sessionsApi.getTrajectory).toHaveBeenCalled();
  });

  it("surfaces first fetch error and stops interval", async () => {
    vi.spyOn(sessionsApi, "getTrajectory").mockRejectedValue(new Error("network"));
    const { result } = renderHook(() =>
      usePollTrajectory("sid", { enabled: true, pollIntervalMs: 50 }),
    );
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.detail).toBe("network");
    const calls = vi.mocked(sessionsApi.getTrajectory).mock.calls.length;
    await new Promise((r) => setTimeout(r, 120));
    expect(vi.mocked(sessionsApi.getTrajectory).mock.calls.length).toBe(calls);
  });
});
