import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExceptionCard } from "@/components/session/ExceptionCard";
import type { ExceptionRecord } from "@/types";

const ex: ExceptionRecord = {
  exception_id: "e-1",
  severity: "critical",
  field: "gross_weight",
  description: "Weights disagree between documents.",
  evidence: {
    doc_a: "bol",
    val_a: 1200,
    doc_b: "invoice",
    val_b: 1180,
  },
};

describe("ExceptionCard", () => {
  it("renders severity and evidence", () => {
    render(<ExceptionCard exception={ex} />);
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("gross_weight")).toBeInTheDocument();
    expect(screen.getByText("Weights disagree between documents.")).toBeInTheDocument();
    expect(screen.getByText("bol")).toBeInTheDocument();
    expect(screen.getByText("invoice")).toBeInTheDocument();
    expect(screen.getByText("1200")).toBeInTheDocument();
    expect(screen.getByText("1180")).toBeInTheDocument();
  });
});
