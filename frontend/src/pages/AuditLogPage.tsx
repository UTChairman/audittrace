import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listReviewActions } from "../api/client";
import type { ReviewAction } from "../types/api";
import { actionLabel, fieldLabel, formatFieldValue, isMoneyField, reviewStatusLabel } from "../labels";

export function AuditLogPage() {
  const [actions, setActions] = useState<ReviewAction[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listReviewActions()
      .then(setActions)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load audit log");
      });
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="font-display text-3xl tracking-tight">Audit log</h1>
      <p className="text-ink/65">
        Approvals and rejections record the status change. Edits record the old and new values.
      </p>
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
                    {action.filename ?? `Document ${action.document_id}`}
                  </Link>
                </td>
                <td className="px-4 py-3">{fieldLabel(action.field_name)}</td>
                <td className="px-4 py-3">{actionLabel(action.action)}</td>
                <td className="px-4 py-3">{formatLogValue(action, action.previous_value)}</td>
                <td className="px-4 py-3">{formatLogValue(action, action.new_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {actions.length === 0 && <p className="px-4 py-6 text-ink/55">No review actions yet.</p>}
      </div>
    </div>
  );
}

function formatLogValue(action: ReviewAction, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (action.action === "approve" || action.action === "reject" || action.action === "reset") {
    if (typeof value === "string" && ["pending", "approved", "rejected", "edited"].includes(value)) {
      return reviewStatusLabel(value);
    }
  }
  if (action.field_name && isMoneyField(action.field_name)) {
    return formatFieldValue(action.field_name, value, null);
  }
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}
