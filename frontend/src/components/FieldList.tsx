import { useState } from "react";
import type { ExtractedField } from "../types/api";
import { reviewField } from "../api/client";
import { VerificationBadge } from "./VerificationBadge";
import {
  editSeedValue,
  fieldLabel,
  formatFieldValue,
  reviewStatusLabel,
} from "../labels";

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
  const [error, setError] = useState<string | null>(null);
  const suggested = fields.find((field) => field.field_name === "currency_suggested");
  const currencyField = fields.find((field) => field.field_name === "currency");
  const currency =
    typeof currencyField?.value === "string"
      ? currencyField.value
      : typeof suggested?.value === "string"
        ? suggested.value
        : null;

  async function act(
    field: ExtractedField,
    action: "approve" | "reject" | "edit" | "reset",
    value?: unknown
  ) {
    try {
      await reviewField(documentId, {
        field_name: field.field_name,
        action,
        value,
      });
      setError(null);
      onReviewed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed");
    }
  }

  return (
    <div className="space-y-2">
      {error && (
        <p className="rounded-md border border-high/30 bg-high/10 px-3 py-2 text-sm text-high">{error}</p>
      )}
      {fields
        .filter((field) => field.field_name !== "currency_suggested")
        .map((field) => {
          const active = selectedField === field.field_name;
          const missing = field.verification_status === "not_present";
          const approved = field.review_status === "approved";
          const rejected = field.review_status === "rejected";
          const pending = field.review_status === "pending";
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
                  <p className="text-xs font-medium tracking-wide text-ink/50">
                    {fieldLabel(field.field_name)}
                  </p>
                  <p className="font-display text-lg leading-snug tracking-tight">
                    {missing ? "—" : formatFieldValue(field.field_name, field.value, currency)}
                  </p>
                </div>
                <VerificationBadge field={field} />
              </div>
              <p className="mt-1 text-xs text-ink/55">
                {missing ? null : `Confidence ${(field.confidence_score * 100).toFixed(0)}% · `}
                {reviewStatusLabel(field.review_status)}
              </p>
              {field.supporting_quote && !missing && (
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
                  <p>{formatFieldValue(suggested.field_name, suggested.value, null)}</p>
                  {suggested.supporting_quote && (
                    <p className="italic text-ink/70">Evidence: “{suggested.supporting_quote}”</p>
                  )}
                </div>
              )}
              {field.review_status === "edited" &&
                field.original_ai_value !== null &&
                field.original_ai_value !== undefined && (
                  <p className="mt-1 text-xs text-ink/50">
                    Original AI value:{" "}
                    {formatFieldValue(field.field_name, field.original_ai_value, currency)}
                  </p>
                )}
              <div className="mt-2 flex flex-wrap gap-2">
                <ActionChip
                  label="Approve"
                  disabled={approved}
                  onClick={() => void act(field, "approve")}
                />
                <ActionChip
                  label="Reject"
                  disabled={rejected}
                  onClick={() => void act(field, "reject")}
                />
                <ActionChip
                  label="Edit"
                  onClick={() => {
                    setEditName(field.field_name);
                    setEditValue(editSeedValue(field.field_name, field.value));
                  }}
                />
                {!pending && (
                  <ActionChip label="Reset to pending" onClick={() => void act(field, "reset")} />
                )}
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

function ActionChip({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <span
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        if (!disabled) onClick();
      }}
      onKeyDown={(event) => {
        if (!disabled && event.key === "Enter") onClick();
      }}
      className={`rounded border px-2 py-1 text-xs ${
        disabled
          ? "cursor-not-allowed border-line/70 bg-paper text-ink/35"
          : "border-line hover:bg-paper active:opacity-70"
      }`}
    >
      {label}
    </span>
  );
}
