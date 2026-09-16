export type BoundingBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type DocumentPage = {
  page_number: number;
  image_path: string;
  width_px: number;
  height_px: number;
};

export type DocumentSummary = {
  id: number;
  filename: string;
  content_type: string;
  file_hash: string;
  file_size_bytes: number;
  status: string;
  page_count: number;
  ocr_cache_id: number | null;
  duplicate_of_document_id: number | null;
  error_message: string | null;
  document_type: string | null;
  pages: DocumentPage[];
};

export type ValidationFlag = {
  reason: string;
  severity: "low" | "medium" | "high";
};

export type ExtractedField = {
  field_name: string;
  value: unknown;
  source_paragraph_ids: string[];
  supporting_quote: string | null;
  verification_status: "verified" | "weak" | "unverified";
  validation_flags: ValidationFlag[];
  confidence_score: number;
  review_status: string;
  original_ai_value: unknown;
  edited_value: unknown;
};

export type Extraction = {
  document_id: number;
  status: string;
  document_type: string | null;
  schema_type: string | null;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  fields: ExtractedField[];
};

export type OcrParagraph = {
  stable_id: string;
  page_number: number;
  text: string;
  bbox: BoundingBox;
  confidence: number | null;
};

export type OcrPage = {
  page_number: number;
  width_px: number;
  height_px: number;
  paragraphs: OcrParagraph[];
};

export type DocumentOcr = {
  document_id: number;
  status: string;
  pages: OcrPage[];
};

export type FieldCitation = {
  document_id: number;
  field_name: string;
  value: unknown;
  source_paragraph_ids: string[];
  supporting_quote: string | null;
};

export type AuditFinding = {
  id: number;
  check_type: string;
  severity: "high" | "medium" | "low";
  explanation: string;
  document_id: number;
  related_document_id: number | null;
  field_citations: FieldCitation[];
  created_at: string;
};

export type ReviewAction = {
  id: number;
  document_id: number;
  field_id: number | null;
  field_name: string | null;
  action: string;
  actor: string;
  previous_value: unknown;
  new_value: unknown;
  note: string | null;
  created_at: string;
};
