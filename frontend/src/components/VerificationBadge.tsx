import type { ExtractedField } from "../types/api";

export function VerificationBadge({ field }: { field: ExtractedField }) {
  const isAmbiguous = field.validation_flags.some((flag) =>
    flag.reason.startsWith("ambiguous_currency_symbol")
  );
  const tone =
    field.verification_status === "verified"
      ? "bg-forest/10 text-forest"
      : field.verification_status === "weak"
        ? "bg-weak/15 text-weak"
        : "bg-high/10 text-high";
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${tone}`}>
        {field.verification_status}
      </span>
      {isAmbiguous && (
        <span className="rounded-full bg-weak/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-weak">
          Ambiguous currency
        </span>
      )}
    </span>
  );
}
