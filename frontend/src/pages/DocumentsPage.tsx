import { useEffect, useMemo, useState } from "react";
import { listDocuments, uploadFiles } from "../api/client";
import type { DocumentSummary } from "../types/api";
import { StatusBadge } from "../components/StatusBadge";
import { Link } from "react-router-dom";

const TERMINAL = new Set(["extracted", "failed", "extraction_failed"]);

export function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function refresh() {
    try {
      setDocuments(await listDocuments());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load documents");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const busy = useMemo(
    () => documents.some((document) => !TERMINAL.has(document.status)),
    [documents]
  );

  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [busy]);

  async function onFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    try {
      await uploadFiles(Array.from(fileList));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-3xl tracking-tight">Documents</h1>
        <p className="text-ink/65">Upload invoices and purchase orders, then open a file to review citations.</p>
      </div>
      <label
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          void onFiles(event.dataTransfer.files);
        }}
        className={`flex cursor-pointer flex-col items-center rounded-lg border border-dashed px-6 py-10 shadow-panel transition-opacity duration-150 ${
          dragOver ? "border-forest bg-forest/5" : "border-line bg-elevated hover:bg-surface"
        }`}
      >
        <span className="font-medium">Drop PDF or image files here</span>
        <span className="text-sm text-ink/55">or click to browse</span>
        <input
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg"
          className="hidden"
          onChange={(event) => void onFiles(event.target.files)}
        />
      </label>
      {error && (
        <p className="rounded-md border border-high/30 bg-high/10 px-3 py-2 text-sm text-high">{error}</p>
      )}
      <div className="overflow-hidden rounded-lg border border-line bg-elevated shadow-panel">
        <table className="w-full text-sm">
          <thead className="bg-paper text-left text-xs uppercase tracking-wide text-ink/55">
            <tr>
              <th className="px-4 py-2">ID</th>
              <th className="px-4 py-2">File</th>
              <th className="px-4 py-2">Type</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Error</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.id} className="border-t border-line">
                <td className="px-4 py-3">{document.id}</td>
                <td className="px-4 py-3">
                  <Link
                    className="font-medium text-forest hover:opacity-80 active:opacity-60"
                    to={`/documents/${document.id}`}
                  >
                    {document.filename}
                  </Link>
                  {document.duplicate_of_document_id && (
                    <span className="ml-2 text-xs text-ink/50">
                      copy of #{document.duplicate_of_document_id}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">{document.document_type ?? "—"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={document.status} />
                </td>
                <td className="px-4 py-3 text-high">{document.error_message ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
