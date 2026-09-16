import type {
  AuditFinding,
  DocumentOcr,
  DocumentSummary,
  Extraction,
  ReviewAction,
} from "../types/api";

const API = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return (await response.json()) as T;
}

export function pageImageUrl(documentId: number, pageNumber: number): string {
  return `${API}/documents/${documentId}/pages/${pageNumber}/image`;
}

export function listDocuments() {
  return request<DocumentSummary[]>("/documents");
}

export function getDocument(id: number) {
  return request<DocumentSummary>(`/documents/${id}`);
}

export function getOcr(id: number) {
  return request<DocumentOcr>(`/documents/${id}/ocr`);
}

export function getExtraction(id: number) {
  return request<Extraction>(`/documents/${id}/extraction`);
}

export function listFindings() {
  return request<{ findings: AuditFinding[] }>("/findings").then((body) => body.findings);
}

export function getFinding(id: number) {
  return request<AuditFinding>(`/findings/${id}`);
}

export function listReviewActions(documentId?: number) {
  const query = documentId ? `?document_id=${documentId}` : "";
  return request<{ actions: ReviewAction[] }>(`/review-actions${query}`).then(
    (body) => body.actions
  );
}

export function uploadFiles(files: File[]) {
  const data = new FormData();
  for (const file of files) {
    data.append("files", file);
  }
  return request<{ documents: { id: number; filename: string; status: string }[] }>(
    "/upload",
    { method: "POST", body: data }
  );
}

export function reviewField(
  documentId: number,
  payload: { field_name: string; action: "approve" | "reject" | "edit"; value?: unknown; note?: string }
) {
  return request<ReviewAction>(`/documents/${documentId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function runAudit() {
  return request<{ finding_count: number }>("/audit/run", { method: "POST" });
}
