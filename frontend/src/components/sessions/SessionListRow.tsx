import { Link } from "react-router-dom";

import type { SessionSummary, SessionStatus } from "@/types";

import { formatAbsolute, formatRelative } from "@/lib/time";

function statusBadgeClass(status: SessionStatus): string {
  switch (status) {
    case "processing":
      return "bg-status-processing/15 text-status-processing border-status-processing/30";
    case "complete":
      return "bg-status-complete/15 text-status-complete border-status-complete/30";
    case "failed":
      return "bg-status-failed/15 text-status-failed border-status-failed/30";
    case "awaiting_review":
      return "bg-status-awaiting_review/15 text-status-awaiting_review border-status-awaiting_review/30";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

function truncateId(id: string): string {
  if (id.length <= 14) return id;
  return `${id.slice(0, 8)}…`;
}

export function SessionListRow(props: { row: SessionSummary; nowMs?: number }) {
  const { row, nowMs } = props;
  const abs = formatAbsolute(row.created_at);
  const rel = formatRelative(row.created_at, nowMs ?? Date.now());
  const c = row.critical_count;
  const w = row.warning_count;
  const i = row.info_count;
  const allUnknown = c == null && w == null && i == null;
  const cv = c ?? 0;
  const wv = w ?? 0;
  const iv = i ?? 0;
  const allZero = cv === 0 && wv === 0 && iv === 0;
  const showDash = allUnknown || allZero;

  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50/80">
      <td className="px-3 py-3 text-sm text-slate-700" title={abs}>
        {rel}
      </td>
      <td className="px-3 py-3">
        <Link
          to={`/sessions/${encodeURIComponent(row.session_id)}`}
          className="font-mono text-sm text-slate-900 underline decoration-slate-300 hover:decoration-slate-600"
          title={row.session_id}
        >
          {truncateId(row.session_id)}
        </Link>
      </td>
      <td className="px-3 py-3">
        <span
          className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${statusBadgeClass(row.status)}`}
        >
          {row.status.replace("_", " ")}
        </span>
      </td>
      <td className="px-3 py-3">
        {showDash ? (
          <span className="text-sm text-slate-500">—</span>
        ) : (
          <div className="flex flex-wrap gap-1">
            {cv > 0 ? (
              <span className="rounded bg-severity-critical/15 px-2 py-0.5 font-mono text-xs text-severity-critical">
                C {cv}
              </span>
            ) : null}
            {wv > 0 ? (
              <span className="rounded bg-severity-warning/15 px-2 py-0.5 font-mono text-xs text-severity-warning">
                W {wv}
              </span>
            ) : null}
            {iv > 0 ? (
              <span className="rounded bg-severity-info/15 px-2 py-0.5 font-mono text-xs text-severity-info">
                I {iv}
              </span>
            ) : null}
          </div>
        )}
      </td>
      <td className="px-3 py-3 text-center text-sm">
        {row.needs_human_review ? (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
            Review
          </span>
        ) : (
          <span className="text-slate-400">—</span>
        )}
      </td>
      <td className="px-3 py-3 text-right font-mono text-sm text-slate-700">
        {row.iteration_count}
      </td>
    </tr>
  );
}
