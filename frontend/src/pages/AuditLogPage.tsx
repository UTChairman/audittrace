import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listReviewActions } from "../api/client";
import type { ReviewAction } from "../types/api";

export function AuditLogPage() {
  const [actions, setActions] = useState<ReviewAction[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listReviewActions().then(setActions).catch((err) => {
      setError(err instanceof Error ? err.message : "Could not load audit log");
    });
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="font-display text-3xl tracking-tight">Audit log</h1>
      <p className="text-ink/65">Every approve, reject, and edit is recorded with the previous and new values.</p>
      {error && <p className="text-high">{error}</p>}
      <div className="overflow-hidden rounded-lg border border-line bg-elevated shadow-panel">
        <table className="w-full text-sm">
          <thead className="bg-paper text-left text-xs uppercase tracking-wide text-ink/55">
            <tr>
              <th className="px-4 py-2">When</th>
              <th className="px-4 py-2">Document</th>
              <th className="px-4 py-2">Field</th>
              <th className="px-4 py-2">Action</th>
              <th className="px-4 py-2">From</th>
              <th className="px-4 py-2">To</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((action) => (
              <tr key={action.id} className="border-t border-line">
                <td className="px-4 py-3 text-ink/60">{action.created_at.replace("T", " ").slice(0, 19)}</td>
                <td className="px-4 py-3">
                  <Link className="text-forest hover:opacity-80" to={`/documents/${action.document_id}`}>
                    #{action.document_id}
                  </Link>
                </td>
                <td className="px-4 py-3">{action.field_name ?? "—"}</td>
                <td className="px-4 py-3">{action.action}</td>
                <td className="px-4 py-3">{formatValue(action.previous_value)}</td>
                <td className="px-4 py-3">{formatValue(action.new_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {actions.length === 0 && <p className="px-4 py-6 text-ink/55">No review actions yet.</p>}
      </div>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}
