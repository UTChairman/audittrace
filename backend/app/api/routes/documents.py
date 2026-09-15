from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ocr import DocumentOcrOut, DocumentOut
from app.services.upload import get_document, get_document_ocr

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}", response_model=DocumentOut)
def read_document(document_id: int, db: Session = Depends(get_db)) -> DocumentOut:
    return get_document(db, document_id)


@router.get("/{document_id}/ocr", response_model=DocumentOcrOut)
def read_document_ocr(document_id: int, db: Session = Depends(get_db)) -> DocumentOcrOut:
    return get_document_ocr(db, document_id)
