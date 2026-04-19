import { describe, expect, it } from "vitest";

import { mergeTrajectoryItems } from "@/components/session/TrajectoryTimeline";
import type { PlannerDecision, ToolCall } from "@/types";

describe("mergeTrajectoryItems", () => {
  it("orders by iteration then timestamp within iteration", () => {
    const pLate: PlannerDecision = {
      iteration: 1,
      chosen_tools: ["t"],
      rationale: "late planner",
      terminate: false,
      created_at: "2020-01-01T00:00:02.000Z",
    };
    const pEarly: PlannerDecision = {
      iteration: 1,
      chosen_tools: [],
      rationale: "early planner",
      terminate: false,
      created_at: "2020-01-01T00:00:01.000Z",
    };
    const toolMid: ToolCall = {
      tool_call_id: "c1",
      iteration: 1,
      tool_name: "read",
      args: {},
      result: null,
      started_at: "2020-01-01T00:00:01.500Z",
      completed_at: "2020-01-01T00:00:01.600Z",
      duration_ms: 100,
      status: "success",
      error: null,
    };
    const p0: PlannerDecision = {
      iteration: 0,
      chosen_tools: [],
      rationale: "iter 0",
      terminate: false,
      created_at: "2020-01-01T00:00:00.000Z",
    };
    const merged = mergeTrajectoryItems([pLate, p0, pEarly], [toolMid]);
    expect(merged.map((m) => m.kind)).toEqual([
      "planner",
      "planner",
      "tool",
      "planner",
    ]);
    expect(merged[1].kind === "planner" && merged[1].decision.rationale).toBe("early planner");
    expect(merged[2].kind === "tool" && merged[2].call.tool_name).toBe("read");
    expect(merged[3].kind === "planner" && merged[3].decision.rationale).toBe("late planner");
  });
});
