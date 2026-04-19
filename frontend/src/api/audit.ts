import { requestJson } from "@/api/client";
import type { AuditResponse } from "@/types";

export async function startAudit(sessionId: string): Promise<AuditResponse> {
  return requestJson<AuditResponse>("/audit", {
    method: "POST",
    body: { session_id: sessionId },
  });
}
