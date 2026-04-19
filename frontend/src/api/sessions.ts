import { requestJson } from "@/api/client";
import type { AuditSession, SessionListResponse, TrajectoryResponse } from "@/types";

export async function listSessions(): Promise<SessionListResponse> {
  return requestJson<SessionListResponse>("/sessions", { method: "GET" });
}

export async function getSession(sessionId: string): Promise<AuditSession> {
  return requestJson<AuditSession>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: "GET",
  });
}

export async function getTrajectory(sessionId: string): Promise<TrajectoryResponse> {
  return requestJson<TrajectoryResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/trajectory`,
    { method: "GET" },
  );
}
