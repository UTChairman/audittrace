import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentClassification,
    ExtractedField,
    Extraction,
    SessionLocal,
)
from app.llm.base import LLMError, LLMProvider
from app.llm.gemini import get_llm_provider
from app.schemas.extraction import (
    ExtractedFieldOut,
    ExtractionOut,
    InvoiceExtraction,
    PurchaseOrderExtraction,
    ValidationFlag,
)
from app.services.extraction.classifier import classify_document
from app.services.extraction.extractor import (
    extract_invoice,
    extract_purchase_order,
    verify_invoice_extraction,
    verify_purchase_order_extraction,
)
from app.services.extraction.verification import FieldVerification
from app.services.ocr.repository import list_paragraphs_with_stable_ids

logger = logging.getLogger(__name__)

EXTRACTABLE_STATUSES = {
    "ocr_complete",
    "extracted",
    "extraction_failed",
    "extracting",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mark_status(db: Session, document: Document, status: str, error: str | None = None) -> None:
    document.status = status
    document.error_message = error
    document.updated_at = _utcnow()
    db.commit()


def _log_tokens(document_id: int, stage: str, model: str, input_tokens: int | None, output_tokens: int | None) -> None:
    logger.info(
        "Document %s %s token usage model=%s input=%s output=%s",
        document_id,
        stage,
        model,
        input_tokens,
        output_tokens,
    )


def _save_classification(
    db: Session,
    document: Document,
    document_type: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> DocumentClassification:
    existing = (
        db.query(DocumentClassification)
        .filter(DocumentClassification.document_id == document.id)
        .first()
    )
    if existing is None:
        existing = DocumentClassification(document_id=document.id)
        db.add(existing)
    existing.document_type = document_type
    existing.model = model
    existing.input_tokens = input_tokens
    existing.output_tokens = output_tokens
    existing.created_at = _utcnow()
    db.flush()
    return existing


def _save_fields(db: Session, extraction: Extraction, fields: list[FieldVerification]) -> None:
    for field in fields:
        value_json = None if field.value is None else json.dumps(field.value)
        db.add(
            ExtractedField(
                extraction_id=extraction.id,
                field_name=field.field_name,
                value_json=value_json,
                source_paragraph_ids=json.dumps(field.source_paragraph_ids),
                supporting_quote=field.supporting_quote,
                verification_status=field.verification_status,
                validation_flags=json.dumps(
                    [flag.model_dump() for flag in field.validation_flags]
                ),
                confidence_score=field.confidence_score,
                review_status="pending",
                original_ai_value=value_json,
            )
        )


async def process_document_extraction(
    document_id: int,
    provider: LLMProvider | None = None,
) -> None:
    """Classify a document and extract cited fields after OCR completes."""
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.error("Document %s not found for extraction", document_id)
            return
        if document.status not in EXTRACTABLE_STATUSES:
            logger.info(
                "Skipping extraction for document %s with status %s",
                document_id,
                document.status,
            )
            return
        if document.ocr_cache_id is None:
            _mark_status(db, document, "extraction_failed", "OCR results are missing")
            return

        paragraphs = list_paragraphs_with_stable_ids(db, document)
        if not paragraphs:
            _mark_status(db, document, "extraction_failed", "No OCR paragraphs to extract from")
            return

        _mark_status(db, document, "extracting")
        llm = provider or get_llm_provider()

        classification = await classify_document(llm, paragraphs)
        _log_tokens(
            document_id,
            "classify",
            classification.usage.model,
            classification.usage.input_tokens,
            classification.usage.output_tokens,
        )
        _save_classification(
            db,
            document,
            classification.parsed.document_type,
            classification.usage.model,
            classification.usage.input_tokens,
            classification.usage.output_tokens,
        )
        db.commit()

        document_type = classification.parsed.document_type
        if document_type == "unknown":
            _mark_status(db, document, "extracted")
            logger.info("Document %s classified as unknown; skipping extraction", document_id)
            from app.services.audit.pipeline import run_audit

            run_audit(db)
            return

        if document_type == "invoice":
            result = await extract_invoice(llm, paragraphs)
            fields = verify_invoice_extraction(result.parsed, paragraphs, document.id)
            schema_type = "invoice"
        elif document_type == "purchase_order":
            result = await extract_purchase_order(llm, paragraphs)
            fields = verify_purchase_order_extraction(result.parsed, paragraphs, document.id)
            schema_type = "purchase_order"
        else:
            _mark_status(db, document, "extracted")
            return

        _log_tokens(
            document_id,
            "extract",
            result.usage.model,
            result.usage.input_tokens,
            result.usage.output_tokens,
        )
        raw_text = result.raw_text or (
            result.parsed.model_dump_json()
            if isinstance(result.parsed, (InvoiceExtraction, PurchaseOrderExtraction))
            else json.dumps(result.parsed)
        )
        extraction = Extraction(
            document_id=document.id,
            schema_type=schema_type,
            raw_llm_response=raw_text,
            model=result.usage.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )
        db.add(extraction)
        db.flush()
        _save_fields(db, extraction, fields)
        _mark_status(db, document, "extracted")
        logger.info("Document %s extraction complete as %s", document_id, schema_type)
        from app.services.audit.pipeline import run_audit

        run_audit(db)
    except LLMError as exc:
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            _mark_status(db, document, "extraction_failed", str(exc))
        logger.error("Extraction failed for document %s: %s", document_id, exc)
    except Exception:
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            _mark_status(db, document, "extraction_failed", "Unexpected error during extraction")
        logger.exception("Unexpected extraction failure for document %s", document_id)
    finally:
        db.close()


def get_latest_extraction(db: Session, document_id: int) -> ExtractionOut:
    document = db.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")

    classification = (
        db.query(DocumentClassification)
        .filter(DocumentClassification.document_id == document_id)
        .first()
    )
    extraction = (
        db.query(Extraction)
        .filter(Extraction.document_id == document_id)
        .order_by(Extraction.created_at.desc(), Extraction.id.desc())
        .first()
    )

    fields_out: list[ExtractedFieldOut] = []
    if extraction is not None:
        rows = (
            db.query(ExtractedField)
            .filter(ExtractedField.extraction_id == extraction.id)
            .order_by(ExtractedField.id.asc())
            .all()
        )
        for row in rows:
            value = json.loads(row.value_json) if row.value_json is not None else None
            flags = [ValidationFlag.model_validate(item) for item in json.loads(row.validation_flags)]
            fields_out.append(
                ExtractedFieldOut(
                    field_name=row.field_name,
                    value=value,
                    source_paragraph_ids=json.loads(row.source_paragraph_ids),
                    supporting_quote=row.supporting_quote,
                    verification_status=row.verification_status,
                    validation_flags=flags,
                    confidence_score=row.confidence_score,
                    review_status=row.review_status,
                )
            )

    return ExtractionOut(
        document_id=document.id,
        status=document.status,
        document_type=classification.document_type if classification else None,
        schema_type=extraction.schema_type if extraction else None,
        model=extraction.model if extraction else (classification.model if classification else None),
        input_tokens=extraction.input_tokens if extraction else None,
        output_tokens=extraction.output_tokens if extraction else None,
        fields=fields_out,
    )
