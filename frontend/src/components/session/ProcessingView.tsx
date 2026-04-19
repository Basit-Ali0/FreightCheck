import type { AuditSession, TrajectoryResponse } from "@/types";

import { TrajectoryTimeline } from "@/components/session/TrajectoryTimeline";
import { formatElapsed } from "@/lib/time";

export function ProcessingView(props: {
  session: AuditSession;
  trajectory: TrajectoryResponse | null;
}) {
  const { session, trajectory } = props;
  const iter = trajectory?.iteration_count ?? session.iteration_count;
  const tokens = trajectory?.tokens_used ?? session.tokens_used;
  const elapsed = trajectory?.elapsed_ms ?? session.elapsed_ms;
  const planners = trajectory?.planner_decisions ?? session.planner_decisions;
  const tools = trajectory?.tool_calls ?? session.tool_calls;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center gap-6">
        <div
          className="h-10 w-10 animate-spin rounded-full border-2 border-slate-300 border-t-slate-800"
          aria-hidden
        />
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Audit in progress</h1>
          <p className="mt-1 text-sm text-slate-600">
            Current iteration: <span className="font-mono">{iter}</span>
          </p>
        </div>
        <div className="ml-auto flex gap-6 text-sm text-slate-700">
          <div>
            <p className="text-xs uppercase text-slate-500">Tokens</p>
            <p className="font-mono">{tokens.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-slate-500">Elapsed</p>
            <p className="font-mono">{formatElapsed(elapsed)}</p>
          </div>
        </div>
      </div>
      <TrajectoryTimeline plannerDecisions={planners} toolCalls={tools} mode="live" />
    </div>
  );
}
