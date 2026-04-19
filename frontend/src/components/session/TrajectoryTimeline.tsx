import { useEffect, useMemo, useRef } from "react";

import type { PlannerDecision, ToolCall } from "@/types";

import { PlannerDecisionCard } from "@/components/session/PlannerDecisionCard";
import { ToolCallRow } from "@/components/session/ToolCallRow";

function parseTs(iso: string): number {
  const n = Date.parse(iso);
  return Number.isFinite(n) ? n : 0;
}

export type TimelineMode = "live" | "static";

type Merged =
  | { kind: "planner"; iteration: number; at: number; decision: PlannerDecision }
  | { kind: "tool"; iteration: number; at: number; call: ToolCall };

export function mergeTrajectoryItems(
  plannerDecisions: PlannerDecision[],
  toolCalls: ToolCall[],
): Merged[] {
  const items: Merged[] = [];
  for (const d of plannerDecisions) {
    items.push({
      kind: "planner",
      iteration: d.iteration,
      at: parseTs(d.created_at),
      decision: d,
    });
  }
  for (const c of toolCalls) {
    items.push({
      kind: "tool",
      iteration: c.iteration,
      at: parseTs(c.started_at),
      call: c,
    });
  }
  items.sort((a, b) => a.iteration - b.iteration || a.at - b.at);
  return items;
}

export function TrajectoryTimeline(props: {
  plannerDecisions: PlannerDecision[];
  toolCalls: ToolCall[];
  mode: TimelineMode;
}) {
  const { plannerDecisions, toolCalls, mode } = props;
  const bottomRef = useRef<HTMLDivElement>(null);
  const merged = useMemo(
    () => mergeTrajectoryItems(plannerDecisions, toolCalls),
    [plannerDecisions, toolCalls],
  );

  useEffect(() => {
    if (mode !== "live") return;
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [merged, mode]);

  return (
    <div className="max-h-[480px] space-y-3 overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-3">
      {merged.length === 0 ? (
        <p className="text-sm text-slate-600">No trajectory events yet.</p>
      ) : (
        merged.map((m, idx) => (
          <div key={`${m.kind}-${idx}`}>
            {m.kind === "planner" ? (
              <PlannerDecisionCard decision={m.decision} />
            ) : (
              <ToolCallRow call={m.call} />
            )}
          </div>
        ))
      )}
      <div ref={bottomRef} />
    </div>
  );
}
