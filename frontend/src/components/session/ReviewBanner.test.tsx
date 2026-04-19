import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReviewBanner } from "@/components/session/ReviewBanner";

describe("ReviewBanner", () => {
  it("renders nothing when reasons empty", () => {
    const { container } = render(<ReviewBanner reasons={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders reasons and dismisses", () => {
    render(<ReviewBanner reasons={["Check container IDs"]} />);
    expect(screen.getByText("Review required")).toBeInTheDocument();
    expect(screen.getByText("Check container IDs")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Human review requested")).not.toBeInTheDocument();
  });
});
