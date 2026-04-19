import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "@/App";

describe("App", () => {
  it("renders routed shell with header", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: "FreightCheck" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sessions" })).toBeInTheDocument();
  });
});
