export function RunAuditButton(props: {
  ready: boolean;
  isUploading: boolean;
  isAuditing: boolean;
  onClick: () => void;
}) {
  const { ready, isUploading, isAuditing, onClick } = props;
  const busy = isUploading || isAuditing;
  const disabled = !ready || busy;

  let label = "Run freight audit";
  if (isUploading) label = "Uploading documents…";
  else if (isAuditing) label = "Starting audit…";

  const aria =
    !ready && !busy
      ? "Run freight audit (disabled: add bill of lading, invoice, and packing list PDFs)"
      : busy
        ? label
        : "Run freight audit on the three uploaded PDFs";

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-label={aria}
      title={!ready && !busy ? "Add all three PDFs to enable the audit." : undefined}
      className="rounded-md bg-slate-900 px-8 py-2.5 text-sm font-medium text-white shadow-sm disabled:cursor-not-allowed disabled:bg-slate-400"
    >
      {label}
    </button>
  );
}

export function allSlotsFilled(
  bol: File | null,
  invoice: File | null,
  packingList: File | null,
): boolean {
  return Boolean(bol && invoice && packingList);
}
