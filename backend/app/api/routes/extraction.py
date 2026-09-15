from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Document
from app.db.session import get_db
from app.schemas.extraction import ExtractJobOut, ExtractionOut
from app.services.extraction.pipeline import (
    EXTRACTABLE_STATUSES,
    get_latest_extraction,
    process_document_extraction,
)

router = APIRouter(prefix="/documents", tags=["extraction"])


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
