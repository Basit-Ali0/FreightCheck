import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { listSessions } from "@/api/sessions";
import { useToast } from "@/components/Toast";
import { SessionListRow } from "@/components/sessions/SessionListRow";
import type { SessionSummary } from "@/types";

export function SessionsPage() {
  const { pushError } = useToast();
  const [rows, setRows] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listSessions();
      setRows(res.sessions);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.detail
          : e instanceof Error
            ? e.message
            : "Could not load sessions.";
      pushError(msg);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [pushError]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const nowMs = Date.now();

  return (
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Audit sessions</h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-600">
            All FreightCheck audits for this environment, newest first. Select a session id to open
            the live progress view, final report, and trajectory.
          </p>
        </div>
        <button
          type="button"
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50"
          onClick={() => setRefreshKey((k) => k + 1)}
        >
          Refresh
        </button>
      </div>

      <div className="mt-8 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-sm text-slate-600">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="p-6 text-sm text-slate-600">
            No sessions yet. Upload the three required PDFs from the home page and run an audit to
            create one.
          </p>
        ) : (
          <table className="w-full border-collapse text-left">
            <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2">Session</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Findings</th>
                <th className="px-3 py-2 text-center">Review</th>
                <th className="px-3 py-2 text-right">Iterations</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <SessionListRow key={row.session_id} row={row} nowMs={nowMs} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
