import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listFindings, runAudit } from "../api/client";
import type { AuditFinding } from "../types/api";

const SEVERITY: Record<string, string> = {
  high: "text-high",
  medium: "text-medium",
  low: "text-low",
};

export function FindingsPage() {
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setFindings(await listFindings());
  }

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl tracking-tight">Findings</h1>
          <p className="text-ink/65">Click a finding to open cited evidence on the source pages.</p>
        </div>
        <button
          type="button"
          onClick={() => void runAudit().then(load)}
          className="rounded-md bg-forest px-3 py-2 text-sm font-medium text-paper hover:opacity-90 active:opacity-75"
        >
          Re-run audit
        </button>
      </div>
      {error && <p className="text-high">{error}</p>}
      <div className="space-y-2">
        {findings.map((finding) => (
          <Link
            key={finding.id}
            to={`/findings/${finding.id}`}
            className="block rounded-lg border border-line bg-elevated px-4 py-3 shadow-panel hover:opacity-95 active:opacity-80"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="font-medium">{finding.check_type.replaceAll("_", " ")}</p>
              <span className={`text-xs font-semibold uppercase ${SEVERITY[finding.severity]}`}>
                {finding.severity}
              </span>
            </div>
            <p className="mt-1 text-sm text-ink/75">{finding.explanation}</p>
            <p className="mt-1 text-xs text-ink/50">
              Documents {finding.document_id}
              {finding.related_document_id ? ` and ${finding.related_document_id}` : ""}
            </p>
          </Link>
        ))}
        {findings.length === 0 && <p className="text-ink/60">No findings yet.</p>}
      </div>
    </div>
  );
}
