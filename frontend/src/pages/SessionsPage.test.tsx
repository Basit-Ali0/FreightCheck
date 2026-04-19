import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as sessionsApi from "@/api/sessions";
import { ToastProvider } from "@/components/Toast";
import { ROUTER_FUTURE_FLAGS } from "@/lib/routerFuture";
import { SessionsPage } from "@/pages/SessionsPage";
import type { SessionSummary } from "@/types";

describe("SessionsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches sessions on mount", async () => {
    vi.spyOn(sessionsApi, "listSessions").mockResolvedValue({ sessions: [], total: 0 });
    render(
      <MemoryRouter future={ROUTER_FUTURE_FLAGS}>
        <ToastProvider>
          <SessionsPage />
        </ToastProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(sessionsApi.listSessions).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/No sessions yet/i)).toBeInTheDocument();
  });

  it("renders table after refresh when data exists", async () => {
    const row: SessionSummary = {
      session_id: "abcdefgh-ijklmnop-qrst",
      status: "complete",
      created_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
      critical_count: 0,
      warning_count: 0,
      info_count: 0,
      needs_human_review: false,
      iteration_count: 2,
    };
    vi.spyOn(sessionsApi, "listSessions").mockResolvedValue({ sessions: [row], total: 1 });
    render(
      <MemoryRouter future={ROUTER_FUTURE_FLAGS}>
        <ToastProvider>
          <SessionsPage />
        </ToastProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    expect(screen.getByText("abcdefgh…")).toBeInTheDocument();
  });

  it("refresh triggers another fetch", async () => {
    vi.spyOn(sessionsApi, "listSessions").mockResolvedValue({ sessions: [], total: 0 });
    render(
      <MemoryRouter future={ROUTER_FUTURE_FLAGS}>
        <ToastProvider>
          <SessionsPage />
        </ToastProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(sessionsApi.listSessions).toHaveBeenCalledTimes(1));
    await act(async () => {
      screen.getByRole("button", { name: /Refresh/i }).click();
    });
    await waitFor(() => expect(sessionsApi.listSessions).toHaveBeenCalledTimes(2));
  });
});
