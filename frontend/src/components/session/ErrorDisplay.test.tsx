import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { ErrorDisplay } from "@/components/session/ErrorDisplay";

describe("ErrorDisplay", () => {
  it("renders not_found", () => {
    render(<ErrorDisplay variant="not_found" />);
    expect(screen.getByText("Session not found")).toBeInTheDocument();
  });

  it("renders session_load_failed with retry", () => {
    const onRetry = vi.fn();
    const err = new ApiError("m", 0, "Net", "offline");
    render(<ErrorDisplay variant="session_load_failed" error={err} onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("does not show retry for non-retryable load errors", () => {
    const err = new ApiError("m", 400, "Bad", "nope");
    render(<ErrorDisplay variant="session_load_failed" error={err} onRetry={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("renders polling_paused", () => {
    const err = new ApiError("m", 500, "Http", "bad");
    render(<ErrorDisplay variant="polling_paused" error={err} />);
    expect(screen.getByText("Live updates paused")).toBeInTheDocument();
  });

  it("renders failed_audit", () => {
    render(
      <ErrorDisplay variant="failed_audit" message="oops" sessionId="sid-1" />,
    );
    expect(screen.getByText("Audit failed")).toBeInTheDocument();
    expect(screen.getByText("oops")).toBeInTheDocument();
  });
});
