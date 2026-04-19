import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReportView } from "@/components/session/ReportView";
import type { AuditSession, ExceptionRecord } from "@/types";

function buildSession(over: Partial<AuditSession> = {}): AuditSession {
  const ex1: ExceptionRecord = {
    exception_id: "e1",
    severity: "warning",
    field: "weight",
    description: "Mismatch",
    evidence: { doc_a: "bol", val_a: 1, doc_b: "inv", val_b: 2 },
  };
  const ex2: ExceptionRecord = {
    exception_id: "e2",
    severity: "critical",
    field: "container",
    description: "Bad",
    evidence: { doc_a: "bol", val_a: "x", doc_b: "pl", val_b: "y" },
  };
  return {
    session_id: "s",
    status: "complete",
    created_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
    error_message: null,
    extracted_fields: {
      bol: {
        bill_of_lading_number: "BL-1",
        shipper: "S",
        consignee: "C",
        vessel_name: "V",
        port_of_loading: "A",
        port_of_discharge: "B",
        container_numbers: ["MSKU123"],
        description_of_goods: "G",
        gross_weight: 10,
        incoterm: "FOB",
      },
    },
    extraction_confidence: {
      bol: {
        shipper: {
          field: "shipper",
          value: "S",
          confidence: 0.4,
          rationale: "Low read",
        },
      },
    },
    exceptions: [ex1, ex2],
    report: {
      critical_count: 1,
      warning_count: 1,
      info_count: 0,
      passed_count: 3,
      summary: "Summary line.",
    },
    tool_calls: [],
    planner_decisions: [],
    iteration_count: 1,
    needs_human_review: false,
    review_reasons: [],
    tokens_used: 0,
    elapsed_ms: 0,
    ...over,
  };
}

describe("ReportView", () => {
  it("groups findings by severity order", () => {
    render(<ReportView session={buildSession()} />);
    expect(screen.getByText("Critical findings")).toBeInTheDocument();
    expect(screen.getByText("Warnings")).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 3 });
    const texts = headings.map((h) => h.textContent);
    const critIdx = texts.indexOf("Critical findings");
    const warnIdx = texts.indexOf("Warnings");
    expect(critIdx).toBeGreaterThan(-1);
    expect(warnIdx).toBeGreaterThan(-1);
    expect(critIdx).toBeLessThan(warnIdx);
  });

  it("shows passed validations shell", () => {
    render(<ReportView session={buildSession()} />);
    expect(screen.getByText(/Passed validations \(3\)/)).toBeInTheDocument();
  });

  it("documents tab shows field rows and low-confidence emphasis", () => {
    render(<ReportView session={buildSession()} />);
    fireEvent.click(screen.getByRole("button", { name: "Documents" }));
    expect(screen.getByText("Shipper")).toBeInTheDocument();
    expect(screen.getByText("S")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
  });

  it("trajectory tab shows timeline", () => {
    render(
      <ReportView
        session={buildSession({
          planner_decisions: [
            {
              iteration: 0,
              chosen_tools: ["t"],
              rationale: "go",
              terminate: false,
              created_at: "2020-01-01T00:00:00.000Z",
            },
          ],
          tool_calls: [
            {
              tool_call_id: "1",
              iteration: 0,
              tool_name: "read",
              args: {},
              result: {},
              started_at: "2020-01-01T00:00:01.000Z",
              completed_at: "2020-01-01T00:00:01.100Z",
              duration_ms: 100,
              status: "success",
              error: null,
            },
          ],
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Trajectory" }));
    expect(screen.getByText("read")).toBeInTheDocument();
  });
});
