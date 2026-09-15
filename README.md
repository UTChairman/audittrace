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

### Tests

From `backend/`:

```bash
pytest
```
