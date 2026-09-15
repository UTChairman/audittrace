import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentPage,
    OcrCache,
    SessionLocal,
)
from app.services.ocr.parser import parse_vision_page_response
from app.services.ocr.repository import save_parsed_page
from app.services.ocr.vision import VisionOcrError, annotate_image
from app.services.pdf import PdfProcessingError, render_image_page, render_pdf_to_pages

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _persist_document_pages(db: Session, document_id: int, rendered_pages) -> None:
    for rendered in rendered_pages:
        db.add(
            DocumentPage(
                document_id=document_id,
                page_number=rendered.page_number,
                image_path=str(rendered.image_path),
                width_px=rendered.width_px,
                height_px=rendered.height_px,
            )
        )


def _copy_pages_from_document(db: Session, source_document_id: int, target_document_id: int) -> None:
    source_pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == source_document_id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    for page in source_pages:
        db.add(
            DocumentPage(
                document_id=target_document_id,
                page_number=page.page_number,
                image_path=page.image_path,
                width_px=page.width_px,
                height_px=page.height_px,
            )
        )


def _mark_failed(db: Session, document: Document, message: str) -> None:
    document.status = "failed"
    document.error_message = message
    document.updated_at = _utcnow()
    db.commit()
    logger.error("Document %s failed: %s", document.id, message)


async def process_document_ocr(document_id: int) -> None:
    """Background task: render pages if needed, run OCR, persist parsed structure."""
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.error("Document %s not found for OCR processing", document_id)
            return

        document.status = "processing"
        document.updated_at = _utcnow()
        db.commit()

        existing_cache = (
            db.query(OcrCache).filter(OcrCache.file_hash == document.file_hash).first()
        )
        if existing_cache is not None:
            if document.ocr_cache_id is None:
                document.ocr_cache_id = existing_cache.id
            if document.duplicate_of_document_id is None:
                first_document = (
                    db.query(Document)
                    .filter(Document.file_hash == document.file_hash, Document.id != document.id)
                    .order_by(Document.id.asc())
                    .first()
                )
                if first_document is not None:
                    document.duplicate_of_document_id = first_document.id

            source_document_id = document.duplicate_of_document_id
            if source_document_id is None:
                first_with_pages = (
                    db.query(Document)
                    .filter(
                        Document.file_hash == document.file_hash,
                        Document.id != document.id,
                    )
                    .order_by(Document.id.asc())
                    .first()
                )
                if first_with_pages is not None:
                    source_document_id = first_with_pages.id
                    document.duplicate_of_document_id = first_with_pages.id

            existing_pages = (
                db.query(DocumentPage)
                .filter(DocumentPage.document_id == document_id)
                .count()
            )
            if existing_pages == 0 and source_document_id is not None:
                _copy_pages_from_document(db, source_document_id, document_id)
                source = db.get(Document, source_document_id)
                document.page_count = source.page_count if source else existing_pages

            document.status = "ocr_complete"
            document.updated_at = _utcnow()
            db.commit()
            logger.info("Document %s reused OCR cache %s", document_id, document.ocr_cache_id)
            return

        file_bytes = Path(document.storage_path).read_bytes()
        rendered_pages = _render_pages(document, file_bytes)
        document.page_count = len(rendered_pages)
        _persist_document_pages(db, document.id, rendered_pages)

        ocr_cache = OcrCache(file_hash=document.file_hash)
        db.add(ocr_cache)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            document = db.get(Document, document_id)
            if document is None:
                return
            existing_cache = (
                db.query(OcrCache).filter(OcrCache.file_hash == document.file_hash).first()
            )
            if existing_cache is None:
                document.status = "processing"
                _mark_failed(db, document, "Failed to create or reuse OCR cache")
                return

            document.status = "processing"
            document.ocr_cache_id = existing_cache.id
            if document.duplicate_of_document_id is None:
                first_document = (
                    db.query(Document)
                    .filter(Document.file_hash == document.file_hash, Document.id != document.id)
                    .order_by(Document.id.asc())
                    .first()
                )
                if first_document is not None:
                    document.duplicate_of_document_id = first_document.id

            source_document_id = document.duplicate_of_document_id
            existing_pages = (
                db.query(DocumentPage).filter(DocumentPage.document_id == document_id).count()
            )
            if existing_pages == 0 and source_document_id is not None:
                _copy_pages_from_document(db, source_document_id, document_id)
                source = db.get(Document, source_document_id)
                if source is not None:
                    document.page_count = source.page_count

            document.status = "ocr_complete"
            document.updated_at = _utcnow()
            db.commit()
            logger.info(
                "Document %s reused OCR cache %s after concurrent create",
                document_id,
                existing_cache.id,
            )
            return

        document.ocr_cache_id = ocr_cache.id

        for rendered in rendered_pages:
            image_bytes = rendered.image_path.read_bytes()
            vision_response = await annotate_image(image_bytes)
            parsed = parse_vision_page_response(vision_response, rendered.page_number)
            parsed.width_px = rendered.width_px
            parsed.height_px = rendered.height_px
            save_parsed_page(db, ocr_cache.id, parsed, vision_response)

        document.status = "ocr_complete"
        document.updated_at = _utcnow()
        db.commit()
        logger.info("Document %s OCR complete with cache %s", document_id, ocr_cache.id)
    except (VisionOcrError, PdfProcessingError, ValueError) as exc:
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            _mark_failed(db, document, str(exc))
    except Exception:
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            _mark_failed(db, document, "Unexpected error during OCR processing")
        logger.exception("Unexpected OCR failure for document %s", document_id)
    finally:
        db.close()


def _render_pages(document: Document, file_bytes: bytes):
    from app.utils.files import detect_image_suffix

    if document.content_type == "application/pdf":
        return render_pdf_to_pages(file_bytes, document.id)

    suffix = detect_image_suffix(document.content_type, document.filename)
    return render_image_page(file_bytes, document.id, suffix=suffix)


async def process_uploaded_document(document_id: int) -> None:
    """OCR a document, then classify and extract cited fields."""
    await process_document_ocr(document_id)
    from app.services.extraction.pipeline import process_document_extraction

    await process_document_extraction(document_id)
