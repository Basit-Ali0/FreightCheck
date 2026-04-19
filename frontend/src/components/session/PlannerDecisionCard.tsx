import { useState } from "react";

import type { PlannerDecision } from "@/types";

export function PlannerDecisionCard(props: { decision: PlannerDecision }) {
  const { decision: d } = props;
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-xs text-slate-500">Iteration {d.iteration}</span>
        <span className="text-xs text-slate-600">
          {d.terminate ? "Terminate" : "Continue"}
        </span>
      </div>
      <p className="mt-2 text-slate-800">{d.rationale}</p>
      <button
        type="button"
        className="mt-2 text-xs font-medium text-slate-700 underline"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Hide detail" : "Show detail"}
      </button>
      {open ? (
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-50 p-2 font-mono text-xs text-slate-800">
          {JSON.stringify(
            { chosen_tools: d.chosen_tools, terminate: d.terminate, created_at: d.created_at },
            null,
            2,
          )}
        </pre>
      ) : null}
    </div>
  );
}
