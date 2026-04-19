import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, POLL_TIMEOUT_CODE } from "@/api/client";
import * as sessionsApi from "@/api/sessions";
import { usePollSession } from "@/hooks/usePollSession";
import type { AuditSession, TrajectoryResponse } from "@/types";

const baseSession = (over: Partial<AuditSession>): AuditSession => ({
  session_id: "sid",
  status: "processing",
  created_at: new Date().toISOString(),
  completed_at: null,
  error_message: null,
  extracted_fields: {},
  extraction_confidence: {},
  exceptions: [],
  report: null,
  tool_calls: [],
  planner_decisions: [],
  iteration_count: 0,
  needs_human_review: false,
  review_reasons: [],
  tokens_used: 0,
  elapsed_ms: 0,
  ...over,
});

const baseTraj = (over: Partial<TrajectoryResponse>): TrajectoryResponse => ({
  session_id: "sid",
  status: "processing",
  iteration_count: 1,
  planner_decisions: [],
  tool_calls: [],
  tokens_used: 1,
  elapsed_ms: 10,
  ...over,
});

describe("usePollSession", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("surfaces initial getSession failure", async () => {
    vi.spyOn(sessionsApi, "getSession").mockRejectedValue(
      new ApiError("x", 500, "HttpError", "service down"),
    );
    const { result } = renderHook(() => usePollSession("sid"));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.detail).toBe("service down");
    expect(result.current.loading).toBe(false);
  });

  it("ignores optional trajectory failure when session already terminal", async () => {
    vi.spyOn(sessionsApi, "getSession").mockResolvedValue(
      baseSession({ status: "complete", report: null }),
    );
    vi.spyOn(sessionsApi, "getTrajectory").mockRejectedValue(new Error("traj down"));
    const { result } = renderHook(() => usePollSession("sid"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.session?.status).toBe("complete");
    expect(result.current.error).toBeNull();
  });

  it("loads terminal session without polling loop", async () => {
    vi.spyOn(sessionsApi, "getSession").mockResolvedValue(
      baseSession({ status: "complete", report: null }),
    );
    vi.spyOn(sessionsApi, "getTrajectory").mockResolvedValue(
      baseTraj({ status: "complete" }),
    );
    const { result } = renderHook(() => usePollSession("sid"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.session?.status).toBe("complete");
    expect(sessionsApi.getTrajectory).toHaveBeenCalled();
  });

  it(
    "polls trajectory while processing then refetches session",
    async () => {
      const processing = baseSession({ status: "processing" });
      const complete = baseSession({ status: "complete" });
      vi.spyOn(sessionsApi, "getSession")
        .mockResolvedValueOnce(processing)
        .mockResolvedValueOnce(complete);
      vi.spyOn(sessionsApi, "getTrajectory")
        .mockResolvedValueOnce(baseTraj({ status: "processing", iteration_count: 1 }))
        .mockResolvedValueOnce(baseTraj({ status: "complete", iteration_count: 2 }));

      const { result } = renderHook(() =>
        usePollSession("sid", { pollIntervalMs: 5, overallTimeoutMs: 30_000 }),
      );
      await waitFor(() => expect(result.current.session?.status).toBe("complete"));
      expect(sessionsApi.getTrajectory).toHaveBeenCalledTimes(2);
      expect(sessionsApi.getSession).toHaveBeenCalledTimes(2);
    },
    15_000,
  );

  it(
    "stops after overall timeout",
    async () => {
      vi.spyOn(sessionsApi, "getSession").mockResolvedValue(baseSession({ status: "processing" }));
      vi.spyOn(sessionsApi, "getTrajectory").mockResolvedValue(
        baseTraj({ status: "processing" }),
      );
      const { result } = renderHook(() =>
        usePollSession("sid", { pollIntervalMs: 5, overallTimeoutMs: 500 }),
      );
      await waitFor(() => expect(result.current.error).toBeTruthy());
      expect(result.current.error?.code).toBe(POLL_TIMEOUT_CODE);
      expect(result.current.error?.detail).toContain("1s");
    },
    15_000,
  );

  it("cleans up on unmount without throwing", async () => {
    vi.spyOn(sessionsApi, "getSession").mockImplementation(() => new Promise(() => {}));
    const { unmount } = renderHook(() => usePollSession("sid"));
    unmount();
  });

  it("re-runs fetch when refreshKey increments", async () => {
    vi.spyOn(sessionsApi, "getSession").mockResolvedValue(
      baseSession({ status: "complete", report: null }),
    );
    vi.spyOn(sessionsApi, "getTrajectory").mockResolvedValue(baseTraj({ status: "complete" }));
    const { result, rerender } = renderHook(
      ({ key }: { key: number }) =>
        usePollSession("sid", { refreshKey: key, pollIntervalMs: 5, overallTimeoutMs: 30_000 }),
      { initialProps: { key: 0 } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(sessionsApi.getSession).toHaveBeenCalledTimes(1);
    rerender({ key: 1 });
    await waitFor(() => expect(sessionsApi.getSession).toHaveBeenCalledTimes(2));
  });
});
