const LABELS: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  ocr_complete: "OCR complete",
  extracting: "Extracting",
  extracted: "Extracted",
  failed: "Failed",
  extraction_failed: "Extraction failed",
};

export function StatusBadge({ status }: { status: string }) {
  const failed = status === "failed" || status === "extraction_failed";
  const done = status === "extracted";
  const className = failed
    ? "bg-high/10 text-high"
    : done
      ? "bg-forest/10 text-forest"
      : "bg-medium/10 text-medium";
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {LABELS[status] ?? status}
    </span>
  );
}
