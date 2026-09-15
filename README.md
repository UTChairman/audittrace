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

New uploads run OCR then extraction automatically. Existing OCR-complete documents need the extract POST above.

### Tests

From `backend/`:

```bash
pytest
```
