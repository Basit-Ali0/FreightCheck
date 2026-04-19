import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { startAudit } from "@/api/audit";

describe("audit API", () => {
  it("POST /audit with session_id", async () => {
    vi.spyOn(client, "requestJson").mockResolvedValue({ session_id: "s" });
    await startAudit("abc");
    expect(client.requestJson).toHaveBeenCalledWith("/audit", {
      method: "POST",
      body: { session_id: "abc" },
    });
  });
});
