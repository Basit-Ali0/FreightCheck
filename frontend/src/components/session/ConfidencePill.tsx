export type ConfidenceBand = "high" | "medium" | "low" | "very_low";

export function confidenceBand(confidence: number): ConfidenceBand {
  if (confidence >= 0.9) return "high";
  if (confidence >= 0.7) return "medium";
  if (confidence >= 0.5) return "low";
  return "very_low";
}

/** Row-level emphasis for extracted values (stronger below 0.5 than below 0.9). */
export function confidenceRowHighlightClass(confidence: number): string {
  if (confidence < 0.5) {
    return "bg-red-100/80 ring-2 ring-red-600/40";
  }
  if (confidence < 0.9) {
    return "bg-amber-50/90 ring-1 ring-amber-500/35";
  }
  return "";
}

const BAND_LABEL: Record<ConfidenceBand, string> = {
  high: "High (≥ 0.90)",
  medium: "Medium (0.70–0.89)",
  low: "Low (0.50–0.69)",
  very_low: "Very low (< 0.50)",
};

const BAND_CLASS: Record<ConfidenceBand, string> = {
  high: "bg-confidence-high/15 text-confidence-high border-confidence-high/40",
  medium: "bg-confidence-medium/15 text-confidence-medium border-confidence-medium/40",
  low: "bg-confidence-low/15 text-confidence-low border-confidence-low/40",
  very_low: "bg-confidence-very_low/15 text-confidence-very_low border-confidence-very_low/40",
};

export function ConfidencePill(props: { confidence: number; rationale: string | null }) {
  const { confidence, rationale } = props;
  const band = confidenceBand(confidence);
  const title = `${BAND_LABEL[band]} — ${rationale ?? "No rationale recorded."}`;

  return (
    <span
      title={title}
      className={`inline-flex rounded-full border px-2 py-0.5 font-mono text-xs ${BAND_CLASS[band]}`}
    >
      {(confidence * 100).toFixed(0)}%
    </span>
  );
}
