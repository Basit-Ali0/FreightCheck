import { Link, useNavigate } from "react-router-dom";

import { RunAuditButton, allSlotsFilled } from "@/components/upload/RunAuditButton";
import { UploadSlot } from "@/components/upload/UploadSlot";
import { useToast } from "@/components/Toast";
import { useUploadState } from "@/state/uploadState";

export function UploadPage() {
  const navigate = useNavigate();
  const { pushError } = useToast();
  const bol = useUploadState((s) => s.bol);
  const invoice = useUploadState((s) => s.invoice);
  const packingList = useUploadState((s) => s.packingList);
  const isUploading = useUploadState((s) => s.isUploading);
  const isAuditing = useUploadState((s) => s.isAuditing);
  const error = useUploadState((s) => s.error);
  const setFile = useUploadState((s) => s.setFile);
  const submit = useUploadState((s) => s.submit);

  const ready = allSlotsFilled(bol, invoice, packingList);

  async function onRun() {
    try {
      const sessionId = await submit();
      navigate(`/sessions/${encodeURIComponent(sessionId)}`);
    } catch {
      const msg = useUploadState.getState().error ?? "Upload or audit failed.";
      pushError(msg);
    }
  }

  const busy = isUploading || isAuditing;

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-2xl font-semibold text-slate-900">Document upload</h1>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
        Upload the bill of lading, commercial invoice, and packing list as PDFs (10MB max each).
        FreightCheck extracts structured fields and runs a cross-document audit before you open the
        session workspace.
      </p>

      {error ? (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
          {error}
        </div>
      ) : null}

      <div className="mt-10 flex flex-wrap gap-6">
        <UploadSlot slot="bol" file={bol} disabled={busy} onFile={setFile} />
        <UploadSlot slot="invoice" file={invoice} disabled={busy} onFile={setFile} />
        <UploadSlot slot="packingList" file={packingList} disabled={busy} onFile={setFile} />
      </div>

      <div className="mt-10 flex flex-col items-center gap-6">
        <RunAuditButton
          ready={ready}
          isUploading={isUploading}
          isAuditing={isAuditing}
          onClick={() => void onRun()}
        />
        <Link to="/sessions" className="text-sm font-medium text-slate-700 underline">
          View past sessions
        </Link>
      </div>
    </div>
  );
}
