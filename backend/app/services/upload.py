import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import UPLOADS_DIR, get_settings
from app.db.models import Document, DocumentPage, OcrBlock, OcrCache, OcrParagraph, OcrWord
from app.schemas.ocr import (
    BoundingBox,
    DocumentOcrOut,
    DocumentOut,
    DocumentPageOut,
    OcrBlockOut,
    OcrPageOut,
    OcrParagraphOut,
    OcrWordOut,
    UploadDocumentResult,
    UploadResponse,
)
from app.services.ingestion import process_document_ocr
from app.utils.files import ALLOWED_CONTENT_TYPES, detect_image_suffix, sanitize_filename, to_data_relative_path
from app.utils.hashing import build_stable_id, sha256_hex

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_upload(file: UploadFile, content: bytes) -> str:
    settings = get_settings()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum upload size of {settings.max_upload_size_mb} MB",
        )

    content_type = file.content_type or "application/octet-stream"
    filename = sanitize_filename(file.filename or "upload")

    if content_type not in ALLOWED_CONTENT_TYPES:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            content_type = "application/pdf"
        elif ext == ".png":
            content_type = "image/png"
        elif ext in {".jpg", ".jpeg"}:
            content_type = "image/jpeg"
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Allowed: PDF, PNG, JPG",
            )
    return content_type


async def handle_uploads(
    db: Session,
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results: list[UploadDocumentResult] = []

    for file in files:
        content = await file.read()
        content_type = _validate_upload(file, content)
        filename = sanitize_filename(file.filename or "upload")
        file_hash = sha256_hex(content)

        existing_cache = (
            db.query(OcrCache).filter(OcrCache.file_hash == file_hash).first()
        )
        first_document = (
            db.query(Document)
            .filter(Document.file_hash == file_hash)
            .order_by(Document.id.asc())
            .first()
        )

        document = Document(
            filename=filename,
            content_type=content_type,
            file_hash=file_hash,
            file_size_bytes=len(content),
            storage_path="",
            status="pending",
            duplicate_of_document_id=first_document.id if first_document else None,
            ocr_cache_id=existing_cache.id if existing_cache else None,
        )
        db.add(document)
        db.flush()

        storage_path = UPLOADS_DIR / f"{document.id}_{filename}"
        storage_path.write_bytes(content)
        document.storage_path = str(storage_path)
        document.updated_at = _utcnow()
        db.commit()
        db.refresh(document)

        background_tasks.add_task(process_document_ocr, document.id)
        logger.info("Queued OCR processing for document %s", document.id)

        results.append(
            UploadDocumentResult(
                id=document.id,
                filename=document.filename,
                status=document.status,
                duplicate_of_document_id=document.duplicate_of_document_id,
            )
        )

    return UploadResponse(documents=results)


def get_document(db: Session, document_id: int) -> DocumentOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )

    return DocumentOut(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        file_hash=document.file_hash,
        file_size_bytes=document.file_size_bytes,
        status=document.status,
        page_count=document.page_count,
        ocr_cache_id=document.ocr_cache_id,
        duplicate_of_document_id=document.duplicate_of_document_id,
        error_message=document.error_message,
        pages=[
            DocumentPageOut(
                page_number=page.page_number,
                image_path=to_data_relative_path(page.image_path),
                width_px=page.width_px,
                height_px=page.height_px,
            )
            for page in pages
        ],
    )


def get_document_ocr(db: Session, document_id: int) -> DocumentOcrOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != "ocr_complete" or document.ocr_cache_id is None:
        raise HTTPException(
            status_code=409,
            detail=f"OCR not ready. Current status: {document.status}",
        )

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    page_dimensions = {
        page.page_number: (page.width_px, page.height_px) for page in pages
    }

    blocks = (
        db.query(OcrBlock)
        .filter(OcrBlock.ocr_cache_id == document.ocr_cache_id)
        .order_by(OcrBlock.page_number.asc(), OcrBlock.block_index.asc())
        .all()
    )
    paragraphs = (
        db.query(OcrParagraph)
        .filter(OcrParagraph.ocr_cache_id == document.ocr_cache_id)
        .order_by(
            OcrParagraph.page_number.asc(),
            OcrParagraph.page_paragraph_index.asc(),
        )
        .all()
    )
    paragraph_ids = [paragraph.id for paragraph in paragraphs]
    words_by_paragraph: dict[int, list[OcrWord]] = {pid: [] for pid in paragraph_ids}
    if paragraph_ids:
        for word in (
            db.query(OcrWord)
            .filter(OcrWord.paragraph_id.in_(paragraph_ids))
            .order_by(OcrWord.paragraph_id.asc(), OcrWord.word_index.asc())
            .all()
        ):
            words_by_paragraph[word.paragraph_id].append(word)

    blocks_by_page: dict[int, list[OcrBlockOut]] = {}
    for block in blocks:
        blocks_by_page.setdefault(block.page_number, []).append(
            OcrBlockOut(
                page_number=block.page_number,
                block_index=block.block_index,
                text=block.text,
                bbox=BoundingBox(
                    x=block.bbox_x,
                    y=block.bbox_y,
                    width=block.bbox_width,
                    height=block.bbox_height,
                ),
                confidence=block.confidence,
            )
        )

    paragraphs_by_page: dict[int, list[OcrParagraphOut]] = {}
    for paragraph in paragraphs:
        paragraphs_by_page.setdefault(paragraph.page_number, []).append(
            OcrParagraphOut(
                stable_id=build_stable_id(
                    document_id,
                    paragraph.page_number,
                    paragraph.page_paragraph_index,
                ),
                page_number=paragraph.page_number,
                block_index=paragraph.block_index,
                paragraph_index=paragraph.paragraph_index,
                page_paragraph_index=paragraph.page_paragraph_index,
                text=paragraph.text,
                bbox=BoundingBox(
                    x=paragraph.bbox_x,
                    y=paragraph.bbox_y,
                    width=paragraph.bbox_width,
                    height=paragraph.bbox_height,
                ),
                confidence=paragraph.confidence,
                words=[
                    OcrWordOut(
                        word_index=word.word_index,
                        text=word.text,
                        bbox=BoundingBox(
                            x=word.bbox_x,
                            y=word.bbox_y,
                            width=word.bbox_width,
                            height=word.bbox_height,
                        ),
                        confidence=word.confidence,
                    )
                    for word in words_by_paragraph.get(paragraph.id, [])
                ],
            )
        )

    page_numbers = sorted(set(page_dimensions) | set(blocks_by_page) | set(paragraphs_by_page))
    ocr_pages: list[OcrPageOut] = []
    for page_number in page_numbers:
        width_px, height_px = page_dimensions.get(page_number, (1, 1))
        ocr_pages.append(
            OcrPageOut(
                page_number=page_number,
                width_px=width_px,
                height_px=height_px,
                blocks=blocks_by_page.get(page_number, []),
                paragraphs=paragraphs_by_page.get(page_number, []),
            )
        )

    return DocumentOcrOut(
        document_id=document.id,
        status=document.status,
        pages=ocr_pages,
    )
