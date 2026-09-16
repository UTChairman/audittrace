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

Requeue documents that previously failed extraction:

```bash
curl -X POST "http://localhost:8000/api/extract/pending?include_failed=true"
```

That extracts one document at a time, with a delay between documents (`EXTRACT_PENDING_DELAY_SECONDS`, default 15) so free-tier Gemini rate limits are respected. Transient Gemini 503/500/timeout errors are retried with backoff; if `GEMINI_MODEL` stays unavailable, `GEMINI_FALLBACK_MODEL` is tried once.

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

## Phase 4: Reviewer UI

The React app lives in `frontend/`. Keep the existing API on port 8000; do not start a second backend.

From `frontend/` in PowerShell:

```powershell
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to `http://127.0.0.1:8000`.

Review actions: `POST /api/documents/{id}/review`. Page images: `GET /api/documents/{id}/pages/{n}/image`. Audit log: `GET /api/review-actions`. Export: `/api/export.json` and `/api/export.csv`.

### What to click

1. **Live status** — Documents lists each file with Pending / Processing / Extracting / Extracted / Failed. Error text appears in the Error column. Drop a PDF to watch status poll every 2 seconds.
2. **Click to highlight** — Open `invoice.pdf`. Click `vendor_name` (or Web Design). A box is drawn on the cited paragraph and the page scrolls to it. Resize the window; the box stays aligned.
3. **Badges** — On the invoice, `currency` should show Weak plus **Ambiguous currency**, with suggested **AUD** and Melbourne evidence.
4. **Review + audit log** — Approve, Reject, or Edit a field (edit keeps the original AI value). Open **Audit log** and confirm the action.
5. **Findings evidence** — Open **Findings**, then a two-document finding such as vendor mismatch. Both pages appear side by side with the cited fields highlighted.
6. **Export** — Use **Export JSON** or **Export CSV** in the header.

From `backend/`:

```bash
pytest
```
