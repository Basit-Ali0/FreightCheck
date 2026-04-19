import { useState } from "react";

import type { ToolCall } from "@/types";

export function ToolCallRow(props: { call: ToolCall }) {
  const { call: c } = props;
  const [open, setOpen] = useState(false);
  const ok = c.status === "success";

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-slate-600">{c.tool_name}</span>
        <span className="font-mono text-xs text-slate-400">{c.tool_call_id}</span>
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
            ok ? "bg-emerald-100 text-emerald-900" : "bg-red-100 text-red-900"
          }`}
        >
          {c.status}
        </span>
        <span className="font-mono text-xs text-slate-500">{c.duration_ms} ms</span>
      </div>
      {c.error ? <p className="mt-2 text-xs text-red-800">{c.error}</p> : null}
      <button
        type="button"
        className="mt-2 text-xs font-medium text-slate-700 underline"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Hide args / result" : "Show args / result"}
      </button>
      {open ? (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <pre className="max-h-48 overflow-auto rounded bg-white p-2 font-mono text-xs">
            {JSON.stringify(c.args, null, 2)}
          </pre>
          <pre className="max-h-48 overflow-auto rounded bg-white p-2 font-mono text-xs">
            {JSON.stringify(c.result, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
