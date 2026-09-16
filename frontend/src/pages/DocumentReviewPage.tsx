import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getDocument, getExtraction, getOcr } from "../api/client";
import type { DocumentOcr, DocumentSummary, Extraction, OcrParagraph } from "../types/api";
import { FieldList } from "../components/FieldList";
import { PageViewer } from "../components/PageViewer";
import { StatusBadge } from "../components/StatusBadge";

const TERMINAL = new Set(["extracted", "failed", "extraction_failed"]);

export function DocumentReviewPage() {
  const { documentId } = useParams();
  const id = Number(documentId);
  const [document, setDocument] = useState<DocumentSummary | null>(null);
  const [ocr, setOcr] = useState<DocumentOcr | null>(null);
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [selectedField, setSelectedField] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const doc = await getDocument(id);
    setDocument(doc);
    try {
      setOcr(await getOcr(id));
    } catch {
      setOcr(null);
    }
    try {
      setExtraction(await getExtraction(id));
    } catch {
      setExtraction(null);
    }
  }

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [id]);

  useEffect(() => {
    if (!document || TERMINAL.has(document.status)) return;
    const timer = window.setInterval(() => {
      void load();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [document?.status, id]);

  const paragraphs: OcrParagraph[] = useMemo(
    () => ocr?.pages.flatMap((page) => page.paragraphs) ?? [],
    [ocr]
  );
  const selected = extraction?.fields.find((field) => field.field_name === selectedField) ?? null;
  const highlightedIds = selected?.source_paragraph_ids ?? [];

  useEffect(() => {
    const first = paragraphs.find((paragraph) => highlightedIds.includes(paragraph.stable_id));
    if (first) setPageNumber(first.page_number);
  }, [selectedField]);

  if (!document) {
    return <p className="text-ink/60">{error ?? "Loading…"}</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl tracking-tight">{document.filename}</h1>
          <p className="text-ink/60">
            Document {document.id}
            {document.document_type ? ` · ${document.document_type}` : ""}
          </p>
        </div>
        <StatusBadge status={document.status} />
      </div>
      {document.error_message && (
        <p className="rounded-md border border-high/30 bg-high/10 px-3 py-2 text-sm text-high">
          {document.error_message}
        </p>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="space-y-2">
          {document.pages.length > 1 && (
            <div className="flex gap-2">
              {document.pages.map((page) => (
                <button
                  key={page.page_number}
                  type="button"
                  onClick={() => setPageNumber(page.page_number)}
                  className={`rounded px-2 py-1 text-sm ${
                    pageNumber === page.page_number ? "bg-forest text-paper" : "bg-elevated hover:bg-paper"
                  }`}
                >
                  Page {page.page_number}
                </button>
              ))}
            </div>
          )}
          {document.pages.length > 0 ? (
            <PageViewer
              documentId={document.id}
              pageNumber={pageNumber}
              paragraphs={paragraphs}
              highlightedIds={highlightedIds}
            />
          ) : (
            <p className="rounded-lg border border-line bg-elevated p-6 text-ink/60">
              Page image is not ready yet.
            </p>
          )}
        </div>
        <div>
          <h2 className="mb-2 font-display text-xl tracking-tight">Extracted fields</h2>
          {extraction?.fields?.length ? (
            <FieldList
              documentId={document.id}
              fields={extraction.fields}
              selectedField={selectedField}
              onSelect={setSelectedField}
              onReviewed={() => void load()}
            />
          ) : (
            <p className="text-ink/60">No extracted fields yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
