import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getDocument, getExtraction, getFinding, getOcr } from "../api/client";
import type { AuditFinding, DocumentOcr, DocumentSummary, Extraction, OcrParagraph } from "../types/api";
import { PageViewer } from "../components/PageViewer";
import { StatusBadge } from "../components/StatusBadge";
import { checkTypeLabel, fieldLabel, formatFieldValue } from "../labels";

type Pane = {
  document: DocumentSummary;
  ocr: DocumentOcr | null;
  extraction: Extraction | null;
};

async function loadPane(id: number): Promise<Pane> {
  const document = await getDocument(id);
  let ocr: DocumentOcr | null = null;
  let extraction: Extraction | null = null;
  try {
    ocr = await getOcr(id);
  } catch {
    ocr = null;
  }
  try {
    extraction = await getExtraction(id);
  } catch {
    extraction = null;
  }
  return { document, ocr, extraction };
}

function EvidencePane({
  pane,
  highlightedIds,
}: {
  pane: Pane;
  highlightedIds: string[];
}) {
  const paragraphs: OcrParagraph[] = pane.ocr?.pages.flatMap((page) => page.paragraphs) ?? [];
  const pageNumber =
    paragraphs.find((paragraph) => highlightedIds.includes(paragraph.stable_id))?.page_number ??
    pane.document.pages[0]?.page_number ??
    1;
  const citedFields = (pane.extraction?.fields ?? []).filter((field) =>
    field.source_paragraph_ids.some((id) => highlightedIds.includes(id))
  );
  const currencyField = pane.extraction?.fields.find((field) => field.field_name === "currency");
  const suggested = pane.extraction?.fields.find((field) => field.field_name === "currency_suggested");
  const currency =
    typeof currencyField?.value === "string"
      ? currencyField.value
      : typeof suggested?.value === "string"
        ? suggested.value
        : null;
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-xl tracking-tight">{pane.document.filename}</h2>
          <p className="text-sm text-ink/55">Document {pane.document.id}</p>
        </div>
        <StatusBadge status={pane.document.status} />
      </div>
      {pane.document.pages.length > 0 ? (
        <PageViewer
          documentId={pane.document.id}
          pageNumber={pageNumber}
          paragraphs={paragraphs}
          highlightedIds={highlightedIds}
          intensity="cited"
        />
      ) : (
        <p className="text-ink/60">No page image.</p>
      )}
      <div className="space-y-2">
        {citedFields.map((field) => (
          <div key={field.field_name} className="rounded-md border border-forest/30 bg-forest/5 px-3 py-2">
            <p className="text-xs tracking-wide text-ink/50">{fieldLabel(field.field_name)}</p>
            <p className="font-medium">{formatFieldValue(field.field_name, field.value, currency)}</p>
            {field.supporting_quote && <p className="text-sm italic">“{field.supporting_quote}”</p>}
          </div>
        ))}
      </div>
    </section>
  );
}

export function FindingEvidencePage() {
  const { findingId } = useParams();
  const id = Number(findingId);
  const [finding, setFinding] = useState<AuditFinding | null>(null);
  const [left, setLeft] = useState<Pane | null>(null);
  const [right, setRight] = useState<Pane | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const item = await getFinding(id);
        setFinding(item);
        const first = await loadPane(item.document_id);
        setLeft(first);
        if (item.related_document_id) {
          setRight(await loadPane(item.related_document_id));
        } else {
          setRight(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load finding");
      }
    })();
  }, [id]);

  const idsByDocument = useMemo(() => {
    const map = new Map<number, string[]>();
    for (const citation of finding?.field_citations ?? []) {
      const current = map.get(citation.document_id) ?? [];
      map.set(citation.document_id, [...current, ...citation.source_paragraph_ids]);
    }
    return map;
  }, [finding]);

  if (error) return <p className="text-high">{error}</p>;
  if (!finding || !left) return <p className="text-ink/60">Loading evidence…</p>;

  const twoDocs = Boolean(right);

  return (
    <div className="space-y-4">
      <Link to="/findings" className="text-sm text-forest hover:opacity-80">
        ← Findings
      </Link>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink/50">{finding.severity}</p>
        <h1 className="font-display text-3xl tracking-tight">{checkTypeLabel(finding.check_type)}</h1>
        <p className="mt-1 text-ink/75">{finding.explanation}</p>
      </div>
      <div className={twoDocs ? "grid gap-5 lg:grid-cols-2" : "grid gap-5"}>
        <EvidencePane pane={left} highlightedIds={idsByDocument.get(left.document.id) ?? []} />
        {right && (
          <EvidencePane pane={right} highlightedIds={idsByDocument.get(right.document.id) ?? []} />
        )}
      </div>
    </div>
  );
}
