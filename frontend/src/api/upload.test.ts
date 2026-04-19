import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { uploadDocuments } from "@/api/upload";

describe("upload API", () => {
  it("posts FormData to /upload", async () => {
    vi.spyOn(client, "requestFormData").mockResolvedValue({ session_id: "s" });
    const fd = new FormData();
    await uploadDocuments(fd);
    expect(client.requestFormData).toHaveBeenCalledWith("/upload", fd);
  });
});
