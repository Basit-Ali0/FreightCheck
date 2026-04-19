import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadSlot } from "@/components/upload/UploadSlot";

describe("UploadSlot", () => {
  it("shows invalid file feedback and does not call onFile", () => {
    const onFile = vi.fn();
    render(<UploadSlot slot="bol" file={null} disabled={false} onFile={onFile} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const bad = new File(["hello"], "x.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [bad] } });
    expect(screen.getByText(/Invalid file:/)).toBeInTheDocument();
    expect(onFile).not.toHaveBeenCalled();
  });

  it("disables the file input when the slot is disabled", () => {
    render(<UploadSlot slot="bol" file={null} disabled onFile={vi.fn()} />);
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });
});
