# AuditTrace

AI document extraction with traceable citations back to source document locations.

## Phase 1: Ingestion and OCR

### Setup

1. Copy `.env.example` to `.env` and add your API keys.
2. Create and activate a Python virtual environment in `backend/`.
3. Install dependencies: `pip install -r requirements.txt`
4. Start the API from `backend/`: `uvicorn app.main:app --reload --port 8000`

### Upload

```bash
curl -X POST "http://localhost:8000/api/upload" -F "files=@invoice.pdf"
```

Poll document status:

```bash
curl "http://localhost:8000/api/documents/1"
```

Fetch OCR paragraphs with stable IDs:

```bash
curl "http://localhost:8000/api/documents/1/ocr"
```

Reparse cached OCR from stored Vision responses (no API calls). Run this from the `backend/` folder so Python can import the `scripts` package:

```bash
python -m scripts.reparse_ocr_caches
```

## Phase 2: Extraction with citations

After OCR completes, the API classifies the document with Gemini and extracts Invoice or Purchase Order fields. Every field includes `source_paragraph_ids`, a supporting quote, a verification badge (`verified` / `weak` / `unverified`), validation flags, and a confidence score.

Trigger extraction on a document that already has OCR (this queues Gemini in the background; do not start a second server):

```bash
curl -X POST "http://localhost:8000/api/documents/1/extract"
```

Poll until `status` is `extracted` or `extraction_failed`:

```bash
curl "http://localhost:8000/api/documents/1"
```

Read extracted fields, citations, and verification:

```bash
curl "http://localhost:8000/api/documents/1/extraction"
```

New uploads run OCR then extraction automatically. Existing OCR-complete documents need the extract POST above, or queue all of them at once:

```bash
curl -X POST "http://localhost:8000/api/extract/pending"
```

That extracts one document at a time, with a delay between documents (`EXTRACT_PENDING_DELAY_SECONDS`, default 15) so free-tier Gemini rate limits are respected.

## Phase 3: Audit checks

After extraction, invoices are linked to purchase orders by PO number. The auditor runs vendor, total, date, line-item, and duplicate invoice-number checks. Each finding includes severity, a plain-English explanation, and citations to the extracted fields on both documents.

Re-run checks across all extracted documents:

```bash
curl -X POST "http://localhost:8000/api/audit/run"
```

List all findings:

```bash
curl "http://localhost:8000/api/findings"
```

List findings for one document:

```bash
curl "http://localhost:8000/api/documents/1/findings"
```

### Tests

From `backend/`:

```bash
pytest
```
