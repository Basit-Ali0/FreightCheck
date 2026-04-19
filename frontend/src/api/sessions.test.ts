import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { getSession, getTrajectory, listSessions } from "@/api/sessions";

describe("sessions API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("listSessions calls GET /sessions", async () => {
    vi.spyOn(client, "requestJson").mockResolvedValue({ sessions: [], total: 0 });
    await listSessions();
    expect(client.requestJson).toHaveBeenCalledWith("/sessions", { method: "GET" });
  });

  it("getSession encodes id in path", async () => {
    vi.spyOn(client, "requestJson").mockResolvedValue({ session_id: "a" });
    await getSession("x/y");
    expect(client.requestJson).toHaveBeenCalledWith("/sessions/x%2Fy", { method: "GET" });
  });

  it("getTrajectory encodes id", async () => {
    vi.spyOn(client, "requestJson").mockResolvedValue({ session_id: "a" });
    await getTrajectory("id-1");
    expect(client.requestJson).toHaveBeenCalledWith("/sessions/id-1/trajectory", {
      method: "GET",
    });
  });
});
