import { useState } from "react";
import type { ExtractedField } from "../types/api";
import { reviewField } from "../api/client";
import { VerificationBadge } from "./VerificationBadge";

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

type Props = {
  documentId: number;
  fields: ExtractedField[];
  selectedField: string | null;
  onSelect: (fieldName: string) => void;
  onReviewed: () => void;
};

export function FieldList({ documentId, fields, selectedField, onSelect, onReviewed }: Props) {
  const [editName, setEditName] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const suggested = fields.find((field) => field.field_name === "currency_suggested");

  async function act(field: ExtractedField, action: "approve" | "reject" | "edit", value?: unknown) {
    await reviewField(documentId, {
      field_name: field.field_name,
      action,
      value,
    });
    onReviewed();
  }

  return (
    <div className="space-y-2">
      {fields
        .filter((field) => field.field_name !== "currency_suggested")
        .map((field) => {
          const active = selectedField === field.field_name;
          return (
            <div
              key={field.field_name}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(field.field_name)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelect(field.field_name);
              }}
              className={`block w-full rounded-lg border px-3 py-3 text-left shadow-panel transition-opacity duration-150 hover:opacity-95 active:opacity-80 ${
                active ? "border-forest bg-forest/5" : "border-line bg-elevated"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-ink/50">
                    {field.field_name}
                  </p>
                  <p className="font-display text-lg leading-snug tracking-tight">
                    {displayValue(field.value)}
                  </p>
                </div>
                <VerificationBadge field={field} />
              </div>
              <p className="mt-1 text-xs text-ink/55">
                Confidence {(field.confidence_score * 100).toFixed(0)}% · Review {field.review_status}
              </p>
              {field.supporting_quote && (
                <p className="mt-1 text-sm italic text-ink/70">“{field.supporting_quote}”</p>
              )}
              {field.validation_flags.map((flag) => (
                <p key={flag.reason} className="mt-1 text-xs text-medium">
                  {flag.reason}
                </p>
              ))}
              {field.field_name === "currency" && suggested && (
                <div className="mt-2 rounded-md bg-paper px-2 py-2 text-sm">
                  <p className="text-xs font-semibold uppercase tracking-wide text-high">
                    Suggested currency (unverified)
                  </p>
                  <p>{displayValue(suggested.value)}</p>
                  {suggested.supporting_quote && (
                    <p className="italic text-ink/70">Evidence: “{suggested.supporting_quote}”</p>
                  )}
                </div>
              )}
              {field.review_status === "edited" && field.original_ai_value !== null && field.original_ai_value !== undefined && (
                <p className="mt-1 text-xs text-ink/50">
                  Original AI value: {displayValue(field.original_ai_value)}
                </p>
              )}
              <div className="mt-2 flex flex-wrap gap-2">
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(event) => {
                    event.stopPropagation();
                    void act(field, "approve");
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void act(field, "approve");
                  }}
                  className="rounded border border-line px-2 py-1 text-xs hover:bg-paper active:opacity-70"
                >
                  Approve
                </span>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(event) => {
                    event.stopPropagation();
                    void act(field, "reject");
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void act(field, "reject");
                  }}
                  className="rounded border border-line px-2 py-1 text-xs hover:bg-paper active:opacity-70"
                >
                  Reject
                </span>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(event) => {
                    event.stopPropagation();
                    setEditName(field.field_name);
                    setEditValue(displayValue(field.value));
                  }}
                  className="rounded border border-line px-2 py-1 text-xs hover:bg-paper active:opacity-70"
                >
                  Edit
                </span>
              </div>
              {editName === field.field_name && (
                <div className="mt-2 flex gap-2" onClick={(event) => event.stopPropagation()}>
                  <input
                    value={editValue}
                    onChange={(event) => setEditValue(event.target.value)}
                    className="flex-1 rounded border border-line bg-surface px-2 py-1 text-sm"
                  />
                  <button
                    type="button"
                    className="rounded bg-forest px-2 py-1 text-xs text-paper hover:opacity-90 active:opacity-75"
                    onClick={() => {
                      void act(field, "edit", editValue);
                      setEditName(null);
                    }}
                  >
                    Save
                  </button>
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
