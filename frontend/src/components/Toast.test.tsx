import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "@/components/Toast";

function TriggerWithAction({ onAction }: { onAction: () => void }) {
  const { pushError } = useToast();
  return (
    <button
      type="button"
      onClick={() =>
        pushError("msg", {
          action: { label: "Fix", onClick: onAction },
        })
      }
    >
      trigger
    </button>
  );
}

function Demo() {
  const { pushError } = useToast();
  return (
    <button
      type="button"
      onClick={() =>
        pushError("Something failed", {
          action: { label: "Retry", onClick: () => pushError("second") },
        })
      }
    >
      go
    </button>
  );
}

describe("ToastProvider", () => {
  it("renders action button and runs callback", () => {
    const onSpy = vi.fn();
    render(
      <ToastProvider>
        <TriggerWithAction onAction={onSpy} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "trigger" }));
    fireEvent.click(screen.getByRole("button", { name: "Fix" }));
    expect(onSpy).toHaveBeenCalledTimes(1);
  });

  it("supports nested consumer pattern", () => {
    render(
      <ToastProvider>
        <Demo />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "go" }));
    expect(screen.getByText("Something failed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByText("second")).toBeInTheDocument();
  });
});
