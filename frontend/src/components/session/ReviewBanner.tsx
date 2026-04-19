import { useState } from "react";

export function ReviewBanner(props: { reasons: string[] }) {
  const { reasons } = props;
  const [dismissed, setDismissed] = useState(false);

  if (dismissed || reasons.length === 0) return null;

  return (
    <div className="mb-6 flex items-start justify-between gap-4 rounded-lg border border-status-awaiting_review/40 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <div>
        <p className="font-medium">Review required</p>
        <p className="mt-1 text-xs text-amber-900/80">
          This session needs a human check before it can be closed out.
        </p>
        <ul className="mt-2 list-inside list-disc text-amber-900/90">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        className="shrink-0 rounded border border-amber-300 bg-white px-2 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100"
        onClick={() => setDismissed(true)}
      >
        Dismiss
      </button>
    </div>
  );
}
