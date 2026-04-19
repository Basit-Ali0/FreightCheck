import { useState } from "react";

import type {
  AuditSession,
  BoLFields,
  ExceptionRecord,
  ExceptionSeverity,
  ExtractionConfidence,
  InvoiceFields,
  LineItem,
  PackingListFields,
} from "@/types";

import {
  ConfidencePill,
  confidenceRowHighlightClass,
} from "@/components/session/ConfidencePill";
import { ExceptionCard } from "@/components/session/ExceptionCard";
import { ReviewBanner } from "@/components/session/ReviewBanner";
import { TrajectoryTimeline } from "@/components/session/TrajectoryTimeline";

type Tab = "findings" | "documents" | "trajectory";

const SEVERITY_ORDER: ExceptionSeverity[] = ["critical", "warning", "info"];

const SEVERITY_SECTION_TITLE: Record<ExceptionSeverity, string> = {
  critical: "Critical findings",
  warning: "Warnings",
  info: "Informational",
};

function humanizeField(key: string): string {
  return key
    .split("_")
    .map((p) => (p.length ? p[0].toUpperCase() + p.slice(1) : p))
    .join(" ");
}

function formatScalar(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
    return String(v);
  }
  if (Array.isArray(v)) {
    if (v.length === 0) return "—";
    if (typeof v[0] === "object") return `${v.length} items`;
    return v.join(", ");
  }
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

function groupExceptionsBySeverity(exceptions: ExceptionRecord[]): Record<
  ExceptionSeverity,
  ExceptionRecord[]
> {
  const out: Record<ExceptionSeverity, ExceptionRecord[]> = {
    critical: [],
    warning: [],
    info: [],
  };
  for (const ex of exceptions) {
    out[ex.severity].push(ex);
  }
  return out;
}

function LineItemsTable({ items }: { items: LineItem[] }) {
  if (items.length === 0) {
    return <p className="text-xs text-slate-500">No line items.</p>;
  }
  return (
    <div className="mt-2 overflow-x-auto rounded border border-slate-200 bg-slate-50/80">
      <table className="w-full min-w-[480px] border-collapse text-left text-xs">
        <thead className="bg-slate-100 text-[10px] font-semibold uppercase text-slate-600">
          <tr>
            <th className="px-2 py-1.5">Description</th>
            <th className="px-2 py-1.5">Qty</th>
            <th className="px-2 py-1.5">Unit price</th>
            <th className="px-2 py-1.5">Net weight</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row, i) => (
            <tr key={i} className="border-t border-slate-200">
              <td className="px-2 py-1.5 text-slate-800">{row.description}</td>
              <td className="px-2 py-1.5 font-mono text-slate-700">{row.quantity}</td>
              <td className="px-2 py-1.5 font-mono text-slate-700">{formatScalar(row.unit_price)}</td>
              <td className="px-2 py-1.5 font-mono text-slate-700">{formatScalar(row.net_weight)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentColumn(props: {
  title: string;
  fields: BoLFields | InvoiceFields | PackingListFields | undefined;
  confidence: Record<string, ExtractionConfidence> | undefined;
}) {
  const { title, fields, confidence } = props;
  if (!fields) {
    return (
      <div className="flex min-h-[120px] flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <p className="mt-3 text-sm text-slate-600">No extracted fields for this document.</p>
      </div>
    );
  }

  const entries = Object.entries(fields).filter(([k]) => k !== "line_items") as [
    string,
    unknown,
  ][];

  const lineItems = "line_items" in fields ? fields.line_items : undefined;

  return (
    <div className="flex min-h-0 flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs font-medium uppercase text-slate-500">
              <th className="py-2 pr-2">Field</th>
              <th className="py-2 pr-2">Value</th>
              <th className="py-2">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, val]) => {
              const ec = confidence?.[key];
              const hi = ec ? confidenceRowHighlightClass(ec.confidence) : "";
              return (
                <tr key={key} className={`border-b border-slate-100 ${hi}`}>
                  <td className="py-2 pr-2 align-top text-slate-700">{humanizeField(key)}</td>
                  <td className="py-2 pr-2 align-top font-mono text-xs text-slate-900">
                    {formatScalar(val)}
                  </td>
                  <td className="py-2 align-top">
                    {ec ? (
                      <ConfidencePill confidence={ec.confidence} rationale={ec.rationale} />
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {lineItems && lineItems.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase text-slate-600">Line items</p>
          <LineItemsTable items={lineItems} />
        </div>
      ) : null}
    </div>
  );
}

function DocumentsPanel({ session }: { session: AuditSession }) {
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      <DocumentColumn
        title="Bill of lading"
        fields={session.extracted_fields.bol}
        confidence={session.extraction_confidence.bol}
      />
      <DocumentColumn
        title="Commercial invoice"
        fields={session.extracted_fields.invoice}
        confidence={session.extraction_confidence.invoice}
      />
      <DocumentColumn
        title="Packing list"
        fields={session.extracted_fields.packing_list}
        confidence={session.extraction_confidence.packing_list}
      />
    </div>
  );
}

export function ReportView(props: {
  session: AuditSession;
  showReviewBanner?: boolean;
}) {
  const { session, showReviewBanner } = props;
  const [tab, setTab] = useState<Tab>("findings");
  const report = session.report;

  const stat = (label: string, value: number, color: string) => (
    <div className={`rounded-lg border bg-white px-4 py-3 shadow-sm ${color}`}>
      <p className="text-xs font-medium uppercase text-slate-500">{label}</p>
      <p className="mt-1 font-mono text-2xl font-semibold text-slate-900">{value}</p>
    </div>
  );

  const grouped = groupExceptionsBySeverity(session.exceptions);

  return (
    <div className="mx-auto max-w-6xl">
      {showReviewBanner ? <ReviewBanner reasons={session.review_reasons} /> : null}

      {report ? (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            {stat("Critical", report.critical_count, "border-red-200")}
            {stat("Warning", report.warning_count, "border-amber-200")}
            {stat("Info", report.info_count, "border-sky-200")}
            {stat("Passed", report.passed_count, "border-emerald-200")}
          </div>
          <p className="mb-8 text-lg leading-relaxed text-slate-800">{report.summary}</p>
        </>
      ) : (
        <p className="mb-8 text-slate-600">Report data is not available for this session.</p>
      )}

      <div className="border-b border-slate-200">
        <nav className="-mb-px flex gap-4">
          {(
            [
              ["findings", "Findings"],
              ["documents", "Documents"],
              ["trajectory", "Trajectory"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`border-b-2 px-1 py-3 text-sm font-medium ${
                tab === id
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>

      <div className="mt-6">
        {tab === "findings" ? (
          <div className="space-y-8">
            {report ? (
              <details className="rounded-lg border border-emerald-200 bg-emerald-50/40 p-4 shadow-sm">
                <summary className="cursor-pointer text-sm font-semibold text-emerald-950">
                  Passed validations ({report.passed_count})
                </summary>
                <p className="mt-2 text-xs leading-relaxed text-emerald-900/90">
                  Per-validation detail rows are not returned by the API yet. The count reflects checks
                  that passed inside the audit engine.
                </p>
              </details>
            ) : null}

            {session.exceptions.length === 0 ? (
              <p className="text-sm text-slate-600">No open findings recorded for this session.</p>
            ) : (
              SEVERITY_ORDER.map((sev) => {
                const list = grouped[sev];
                if (list.length === 0) return null;
                return (
                  <section key={sev}>
                    <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-700">
                      {SEVERITY_SECTION_TITLE[sev]}
                    </h3>
                    <div className="space-y-4">
                      {list.map((ex) => (
                        <ExceptionCard key={ex.exception_id} exception={ex} />
                      ))}
                    </div>
                  </section>
                );
              })
            )}
          </div>
        ) : null}

        {tab === "documents" ? <DocumentsPanel session={session} /> : null}

        {tab === "trajectory" ? (
          <TrajectoryTimeline
            plannerDecisions={session.planner_decisions}
            toolCalls={session.tool_calls}
            mode="static"
          />
        ) : null}
      </div>
    </div>
  );
}
