import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import * as auditApi from "@/api/audit";
import * as uploadApi from "@/api/upload";
import { useUploadState } from "@/state/uploadState";

function pdf(name: string): File {
  return new File(["%PDF"], name, { type: "application/pdf", lastModified: Date.now() });
}

describe("useUploadState", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useUploadState.setState({
      bol: null,
      invoice: null,
      packingList: null,
      isUploading: false,
      isAuditing: false,
      error: null,
    });
  });

  it("sets and clears files", () => {
    const f = pdf("a.pdf");
    useUploadState.getState().setFile("bol", f);
    expect(useUploadState.getState().bol).toBe(f);
    useUploadState.getState().clear();
    expect(useUploadState.getState().bol).toBeNull();
  });

  it("runs successful submit flow", async () => {
    vi.spyOn(uploadApi, "uploadDocuments").mockResolvedValue({
      session_id: "s-1",
      message: "ok",
      documents_received: ["bol", "invoice", "packing_list"],
      raw_text_lengths: {},
    });
    vi.spyOn(auditApi, "startAudit").mockResolvedValue({
      session_id: "s-1",
      status: "processing",
      message: "started",
      created_at: new Date().toISOString(),
    });
    useUploadState.getState().setFile("bol", pdf("b.pdf"));
    useUploadState.getState().setFile("invoice", pdf("i.pdf"));
    useUploadState.getState().setFile("packingList", pdf("p.pdf"));
    const id = await useUploadState.getState().submit();
    expect(id).toBe("s-1");
    expect(uploadApi.uploadDocuments).toHaveBeenCalledTimes(1);
    expect(auditApi.startAudit).toHaveBeenCalledWith("s-1");
  });

  it("surfaces upload failure", async () => {
    vi.spyOn(uploadApi, "uploadDocuments").mockRejectedValue(
      new ApiError("nope", 500, "Err", "upload failed"),
    );
    useUploadState.getState().setFile("bol", pdf("b.pdf"));
    useUploadState.getState().setFile("invoice", pdf("i.pdf"));
    useUploadState.getState().setFile("packingList", pdf("p.pdf"));
    await expect(useUploadState.getState().submit()).rejects.toBeInstanceOf(ApiError);
    expect(useUploadState.getState().error).toBe("upload failed");
  });

  it("rejects invalid file in setFile and sets error", () => {
    useUploadState.getState().setFile("bol", new File(["x"], "bad.txt", { type: "text/plain" }));
    expect(useUploadState.getState().error).toBeTruthy();
    expect(useUploadState.getState().bol).toBeNull();
  });

  it("submit throws when files are missing", async () => {
    useUploadState.getState().clear();
    await expect(useUploadState.getState().submit()).rejects.toThrow();
    expect(useUploadState.getState().error).toBeTruthy();
  });

  it("submit rejects when a stored file exceeds size limit", async () => {
    const big = pdf("big.pdf");
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    useUploadState.setState({
      bol: big,
      invoice: pdf("i.pdf"),
      packingList: pdf("p.pdf"),
      error: null,
      isUploading: false,
      isAuditing: false,
    });
    await expect(useUploadState.getState().submit()).rejects.toThrow();
    expect(useUploadState.getState().error).toContain("10MB");
  });

  it("surfaces non-Error failures from upload", async () => {
    vi.spyOn(uploadApi, "uploadDocuments").mockRejectedValue("weird");
    useUploadState.getState().setFile("bol", pdf("b.pdf"));
    useUploadState.getState().setFile("invoice", pdf("i.pdf"));
    useUploadState.getState().setFile("packingList", pdf("p.pdf"));
    await expect(useUploadState.getState().submit()).rejects.toBe("weird");
    expect(useUploadState.getState().error).toBe("Upload or audit failed.");
  });

  it("surfaces audit failure", async () => {
    vi.spyOn(uploadApi, "uploadDocuments").mockResolvedValue({
      session_id: "s-2",
      message: "ok",
      documents_received: [],
      raw_text_lengths: {},
    });
    vi.spyOn(auditApi, "startAudit").mockRejectedValue(
      new ApiError("nope", 400, "Err", "audit failed"),
    );
    useUploadState.getState().setFile("bol", pdf("b.pdf"));
    useUploadState.getState().setFile("invoice", pdf("i.pdf"));
    useUploadState.getState().setFile("packingList", pdf("p.pdf"));
    await expect(useUploadState.getState().submit()).rejects.toBeInstanceOf(ApiError);
    expect(useUploadState.getState().error).toBe("audit failed");
  });
});
