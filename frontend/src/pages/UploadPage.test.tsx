import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { ToastProvider } from "@/components/Toast";
import { ROUTER_FUTURE_FLAGS } from "@/lib/routerFuture";
import { UploadPage } from "@/pages/UploadPage";
import { useUploadState } from "@/state/uploadState";

function pdf(name: string): File {
  return new File(["%PDF"], name, { type: "application/pdf" });
}

describe("UploadPage", () => {
  beforeEach(() => {
    useUploadState.setState({
      bol: null,
      invoice: null,
      packingList: null,
      isUploading: false,
      isAuditing: false,
      error: null,
    });
  });

  it("disables run audit until all slots filled", async () => {
    render(
      <MemoryRouter future={ROUTER_FUTURE_FLAGS}>
        <ToastProvider>
          <UploadPage />
        </ToastProvider>
      </MemoryRouter>,
    );
    const btn = screen.getByRole("button", { name: /Run freight audit/i });
    expect(btn).toBeDisabled();
    await act(async () => {
      useUploadState.getState().setFile("bol", pdf("b.pdf"));
      useUploadState.getState().setFile("invoice", pdf("i.pdf"));
      useUploadState.getState().setFile("packingList", pdf("p.pdf"));
    });
    expect(btn).not.toBeDisabled();
  });
});
