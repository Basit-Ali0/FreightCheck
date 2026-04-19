import type { ReactNode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, createPollTimeoutError } from "@/api/client";
import { ROUTER_FUTURE_FLAGS } from "@/lib/routerFuture";
import type { AuditSession } from "@/types";

const mockUsePollSession = vi.hoisted(() => vi.fn());
const mockPushError = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/usePollSession", () => ({
  usePollSession: (id: string | undefined, opts?: object) => mockUsePollSession(id, opts),
}));

vi.mock("@/components/Toast", () => ({
  useToast: () => ({ pushError: mockPushError }),
  ToastProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

import { SessionDetailPage } from "@/pages/SessionDetailPage";

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

function renderAt(path: string) {
  return render(
    <MemoryRouter future={ROUTER_FUTURE_FLAGS} initialEntries={[path]}>
      <Routes>
        <Route path="/sessions/:id" element={<SessionDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SessionDetailPage", () => {
  beforeEach(() => {
    mockUsePollSession.mockReset();
    mockPushError.mockReset();
  });

  it("dispatches processing view", () => {
    mockUsePollSession.mockReturnValue({
      session: baseSession({ status: "processing" }),
      trajectory: null,
      error: null,
      loading: false,
      notFound: false,
    });
    renderAt("/sessions/sid");
    expect(screen.getByText("Audit in progress")).toBeInTheDocument();
  });

  it("dispatches report view for complete", () => {
    mockUsePollSession.mockReturnValue({
      session: baseSession({
        status: "complete",
        report: {
          critical_count: 0,
          warning_count: 0,
          info_count: 0,
          passed_count: 1,
          summary: "All checks passed for this shipment.",
        },
      }),
      trajectory: null,
      error: null,
      loading: false,
      notFound: false,
    });
    renderAt("/sessions/sid");
    expect(screen.getByText("All checks passed for this shipment.")).toBeInTheDocument();
  });

  it("dispatches error for failed", () => {
    mockUsePollSession.mockReturnValue({
      session: baseSession({ status: "failed", error_message: "LLM error" }),
      trajectory: null,
      error: null,
      loading: false,
      notFound: false,
    });
    renderAt("/sessions/sid");
    expect(screen.getByText("Audit failed")).toBeInTheDocument();
    expect(screen.getByText("LLM error")).toBeInTheDocument();
  });

  it("renders awaiting_review with review banner", () => {
    mockUsePollSession.mockReturnValue({
      session: baseSession({
        status: "awaiting_review",
        review_reasons: ["Container check"],
        report: {
          critical_count: 0,
          warning_count: 1,
          info_count: 0,
          passed_count: 0,
          summary: "Needs review.",
        },
      }),
      trajectory: null,
      error: null,
      loading: false,
      notFound: false,
    });
    renderAt("/sessions/sid");
    expect(screen.getByText("Review required")).toBeInTheDocument();
    expect(screen.getByText("Container check")).toBeInTheDocument();
  });

  it("shows not found state", () => {
    mockUsePollSession.mockReturnValue({
      session: null,
      trajectory: null,
      error: null,
      loading: false,
      notFound: true,
    });
    renderAt("/sessions/sid");
    expect(screen.getByText("Session not found")).toBeInTheDocument();
  });

  it("pushes timeout toast with refresh action", async () => {
    const err = createPollTimeoutError(60_000);
    mockUsePollSession.mockReturnValue({
      session: baseSession({ status: "processing" }),
      trajectory: null,
      error: err,
      loading: false,
      notFound: false,
    });
    renderAt("/sessions/sid");
    await waitFor(() =>
      expect(mockPushError).toHaveBeenCalledWith(
        err.detail,
        expect.objectContaining({
          action: expect.objectContaining({ label: "Refresh", onClick: expect.any(Function) }),
        }),
      ),
    );
    const onRefresh = mockPushError.mock.calls[0][1]?.action?.onClick;
    await act(async () => {
      onRefresh?.();
    });
  });

  it("pushes generic poll error toast without action", () => {
    const err = new ApiError("boom", 500, "HttpError", "Server error");
    mockUsePollSession.mockReturnValue({
      session: baseSession({ status: "processing" }),
      trajectory: null,
      error: err,
      loading: false,
      notFound: false,
    });
    renderAt("/sessions/sid");
    expect(mockPushError).toHaveBeenCalledWith("Server error");
    expect(mockPushError.mock.calls[0][1]).toBeUndefined();
  });
});
