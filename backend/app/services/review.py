import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.db.models import Document, DocumentPage, ExtractedField, Extraction, ReviewAction
from app.schemas.review import ReviewActionListOut, ReviewActionOut, ReviewFieldIn
from app.services.extraction.pipeline import get_latest_extraction


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_json(raw: str | None):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _dump_json(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _latest_field(db: Session, document_id: int, field_name: str) -> ExtractedField:
    extraction = (
        db.query(Extraction)
        .filter(Extraction.document_id == document_id)
        .order_by(Extraction.created_at.desc(), Extraction.id.desc())
        .first()
    )
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction not found")
    field = (
        db.query(ExtractedField)
        .filter(
            ExtractedField.extraction_id == extraction.id,
            ExtractedField.field_name == field_name,
        )
        .first()
    )
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


def apply_review(db: Session, document_id: int, payload: ReviewFieldIn) -> ReviewActionOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    field = _latest_field(db, document_id, payload.field_name)
    previous = field.edited_value if field.edited_value is not None else field.value_json
    new_value = previous
    if payload.action == "approve":
        field.review_status = "approved"
    elif payload.action == "reject":
        field.review_status = "rejected"
    elif payload.action == "edit":
        if field.original_ai_value is None:
            field.original_ai_value = field.value_json
        encoded = _dump_json(payload.value)
        field.edited_value = encoded
        field.value_json = encoded
        field.review_status = "edited"
        new_value = encoded
    action = ReviewAction(
        document_id=document_id,
        field_id=field.id,
        action=payload.action,
        actor=payload.actor or "reviewer",
        previous_value=previous,
        new_value=new_value,
        note=payload.note,
        created_at=_utcnow(),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return _to_out(action, field.field_name)


def list_review_actions(db: Session, document_id: int | None = None) -> ReviewActionListOut:
    query = db.query(ReviewAction)
    if document_id is not None:
        query = query.filter(ReviewAction.document_id == document_id)
    rows = query.order_by(ReviewAction.created_at.desc(), ReviewAction.id.desc()).all()
    field_names = {}
    field_ids = [row.field_id for row in rows if row.field_id is not None]
    if field_ids:
        for field in db.query(ExtractedField).filter(ExtractedField.id.in_(field_ids)).all():
            field_names[field.id] = field.field_name
    return ReviewActionListOut(
        actions=[_to_out(row, field_names.get(row.field_id)) for row in rows]
    )


def _to_out(row: ReviewAction, field_name: str | None) -> ReviewActionOut:
    created = row.created_at.isoformat() if row.created_at else ""
    return ReviewActionOut(
        id=row.id,
        document_id=row.document_id,
        field_id=row.field_id,
        field_name=field_name,
        action=row.action,
        actor=row.actor,
        previous_value=_parse_json(row.previous_value),
        new_value=_parse_json(row.new_value),
        note=row.note,
        created_at=created,
    )


def page_image_response(db: Session, document_id: int, page_number: int) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    page = (
        db.query(DocumentPage)
        .filter(
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
        .first()
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Page image not found")
    stored = Path(page.image_path)
    path = stored if stored.is_absolute() else (DATA_DIR / page.image_path)
    path = path.resolve()
    data_root = DATA_DIR.resolve()
    if path != data_root and data_root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid page image path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Page image file is missing")
    suffix = path.suffix.lower()
    media = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    return FileResponse(path, media_type=media)


def export_payload(db: Session) -> dict:
    from app.db.models import AuditFinding
    from app.services.audit.pipeline import list_findings
    from app.services.upload import list_documents

    documents = list_documents(db)
    payload_documents = []
    for document in documents:
        extraction = None
        try:
            extraction = get_latest_extraction(db, document.id)
        except LookupError:
            extraction = None
        payload_documents.append(
            {
                "document": document.model_dump(),
                "extraction": extraction.model_dump() if extraction else None,
            }
        )
    findings = list_findings(db)
    actions = list_review_actions(db)
    return {
        "documents": payload_documents,
        "findings": [item.model_dump() for item in findings.findings],
        "review_actions": [item.model_dump() for item in actions.actions],
        "finding_count": db.query(AuditFinding).count(),
    }
