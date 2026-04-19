import type { ExceptionRecord } from "@/types";

const SEVERITY_RING: Record<string, string> = {
  critical: "border-l-severity-critical",
  warning: "border-l-severity-warning",
  info: "border-l-severity-info",
};

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 0);
  } catch {
    return String(v);
  }
}

export function ExceptionCard(props: { exception: ExceptionRecord }) {
  const { exception: ex } = props;
  const ring = SEVERITY_RING[ex.severity] ?? "border-l-slate-400";

  return (
    <article
      className={`rounded-md border border-slate-200 bg-white shadow-sm ${ring} border-l-4`}
    >
      <div className="border-b border-slate-100 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-white ${
              ex.severity === "critical"
                ? "bg-severity-critical"
                : ex.severity === "warning"
                  ? "bg-severity-warning"
                  : "bg-severity-info"
            }`}
          >
            {ex.severity}
          </span>
          <span className="font-mono text-xs text-slate-500">{ex.exception_id}</span>
        </div>
        <h3 className="mt-2 text-sm font-semibold text-slate-900">{ex.field}</h3>
        <p className="mt-1 text-sm text-slate-700">{ex.description}</p>
      </div>
      <div className="grid gap-0 sm:grid-cols-2">
        <div className="border-b border-slate-100 px-4 py-3 sm:border-b-0 sm:border-r">
          <p className="text-xs font-medium uppercase text-slate-500">Document A</p>
          <p className="mt-1 font-mono text-xs text-slate-800">{ex.evidence.doc_a}</p>
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-xs text-slate-700">
            {formatVal(ex.evidence.val_a)}
          </pre>
        </div>
        <div className="px-4 py-3">
          <p className="text-xs font-medium uppercase text-slate-500">Document B</p>
          <p className="mt-1 font-mono text-xs text-slate-800">{ex.evidence.doc_b}</p>
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-xs text-slate-700">
            {formatVal(ex.evidence.val_b)}
          </pre>
        </div>
      </div>
    </article>
  );
}
