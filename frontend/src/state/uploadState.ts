import { create } from "zustand";

import { ApiError } from "@/api/client";
import { startAudit } from "@/api/audit";
import { uploadDocuments } from "@/api/upload";

const MAX_BYTES = 10 * 1024 * 1024;

export type DocSlot = "bol" | "invoice" | "packingList";

function validatePdf(file: File): string | null {
  const isPdf =
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) {
    return "Only PDF files are accepted.";
  }
  if (file.size > MAX_BYTES) {
    return `File exceeds ${MAX_BYTES / (1024 * 1024)}MB limit.`;
  }
  return null;
}

export interface UploadState {
  bol: File | null;
  invoice: File | null;
  packingList: File | null;
  isUploading: boolean;
  isAuditing: boolean;
  error: string | null;
  setFile: (slot: DocSlot, file: File | null) => void;
  clear: () => void;
  submit: () => Promise<string>;
}

export const useUploadState = create<UploadState>((set, get) => ({
  bol: null,
  invoice: null,
  packingList: null,
  isUploading: false,
  isAuditing: false,
  error: null,

  setFile(slot, file) {
    if (file) {
      const err = validatePdf(file);
      if (err) {
        set({ error: err });
        return;
      }
    }
    set({ [slot]: file, error: null });
  },

  clear() {
    set({
      bol: null,
      invoice: null,
      packingList: null,
      error: null,
      isUploading: false,
      isAuditing: false,
    });
  },

  async submit() {
    const { bol, invoice, packingList } = get();
    if (!bol || !invoice || !packingList) {
      const msg = "All three PDFs are required.";
      set({ error: msg });
      throw new Error(msg);
    }
    for (const f of [bol, invoice, packingList]) {
      const err = validatePdf(f);
      if (err) {
        set({ error: err });
        throw new Error(err);
      }
    }

    set({ error: null, isUploading: true, isAuditing: false });
    try {
      const fd = new FormData();
      fd.append("bol", bol, bol.name);
      fd.append("invoice", invoice, invoice.name);
      fd.append("packing_list", packingList, packingList.name);
      const up = await uploadDocuments(fd);
      set({ isUploading: false, isAuditing: true });
      await startAudit(up.session_id);
      set({ isAuditing: false });
      return up.session_id;
    } catch (e) {
      set({ isUploading: false, isAuditing: false });
      const message =
        e instanceof ApiError
          ? e.detail
          : e instanceof Error
            ? e.message
            : "Upload or audit failed.";
      set({ error: message });
      throw e;
    }
  },
}));

export { validatePdf };
