import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";

import type { DocSlot } from "@/state/uploadState";
import { validatePdf } from "@/state/uploadState";

const LABELS: Record<DocSlot, string> = {
  bol: "Bill of lading",
  invoice: "Commercial invoice",
  packingList: "Packing list",
};

export function UploadSlot(props: {
  slot: DocSlot;
  file: File | null;
  disabled: boolean;
  onFile: (slot: DocSlot, file: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { slot, file, disabled, onFile } = props;
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (file) setLocalError(null);
  }, [file]);

  const onPick = useCallback(
    (list: FileList | null) => {
      const f = list?.[0] ?? null;
      setLocalError(null);
      if (f) {
        const err = validatePdf(f);
        if (err) {
          setLocalError(err);
          return;
        }
      }
      onFile(slot, f);
    },
    [onFile, slot],
  );

  const onDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (disabled) return;
      onPick(e.dataTransfer.files);
    },
    [disabled, onPick],
  );

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <p className="mb-2 text-sm font-medium text-slate-800">{LABELS[slot]}</p>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onKeyDown={(e) => {
          if (disabled) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onClick={() => {
          if (!disabled) inputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        }}
        onDrop={onDrop}
        className={`flex min-h-[140px] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-3 py-4 text-center transition-colors ${
          disabled
            ? "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400"
            : "border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:bg-slate-50"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          disabled={disabled}
          onChange={(e) => onPick(e.target.files)}
        />
        {file ? (
          <div className="flex flex-col gap-1 text-center">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Selected file
            </span>
            <span className="break-all font-mono text-xs text-slate-900">{file.name}</span>
          </div>
        ) : (
          <div className="flex flex-col gap-1 px-1">
            <span className="text-sm font-medium text-slate-800">No PDF selected</span>
            <span className="text-xs text-slate-500">Click or drop a single PDF (max 10MB)</span>
          </div>
        )}
      </div>
      {localError ? (
        <p className="mt-2 text-xs text-red-700">
          <span className="font-medium">Invalid file:</span> {localError}
        </p>
      ) : null}
    </div>
  );
}
