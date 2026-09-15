from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Document
from app.db.session import get_db
from app.schemas.extraction import ExtractJobOut, ExtractionOut, PendingExtractOut
from app.services.extraction.pipeline import (
    EXTRACTABLE_STATUSES,
    get_latest_extraction,
    list_ocr_complete_document_ids,
    process_document_extraction,
    process_pending_extractions,
)

router = APIRouter(prefix="/documents", tags=["extraction"])
pending_router = APIRouter(tags=["extraction"])


@router.post("/{document_id}/extract", response_model=ExtractJobOut)
async def extract_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ExtractJobOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status not in EXTRACTABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"OCR not ready. Current status: {document.status}",
        )

    document.status = "extracting"
    db.commit()
    background_tasks.add_task(process_document_extraction, document_id)
    return ExtractJobOut(document_id=document.id, status="extracting")


@router.get("/{document_id}/extraction", response_model=ExtractionOut)
def read_extraction(document_id: int, db: Session = Depends(get_db)) -> ExtractionOut:
    try:
        return get_latest_extraction(db, document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc


@pending_router.post("/extract/pending", response_model=PendingExtractOut)
async def extract_pending_documents(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    include_failed: bool = False,
) -> PendingExtractOut:
    settings = get_settings()
    document_ids = list_ocr_complete_document_ids(db, include_failed=include_failed)
    if document_ids:
        db.query(Document).filter(Document.id.in_(document_ids)).update(
            {Document.status: "extracting"},
            synchronize_session=False,
        )
        db.commit()
        background_tasks.add_task(
            process_pending_extractions,
            document_ids,
            settings.extract_pending_delay_seconds,
        )
    return PendingExtractOut(
        queued=len(document_ids),
        document_ids=document_ids,
        delay_seconds=settings.extract_pending_delay_seconds,
    )
