from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ocr import DocumentOut
from app.schemas.review import ReviewActionListOut, ReviewActionOut, ReviewFieldIn
from app.services.review import (
    apply_review,
    export_payload,
    list_review_actions,
    page_image_response,
)
from app.services.upload import get_document, list_documents

router = APIRouter(tags=["review"])


@router.get("/documents", response_model=list[DocumentOut])
def read_documents(db: Session = Depends(get_db)) -> list[DocumentOut]:
    return list_documents(db)


@router.get("/documents/{document_id}/pages/{page_number}/image")
def read_page_image(
    document_id: int,
    page_number: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    return page_image_response(db, document_id, page_number)


@router.post(
    "/documents/{document_id}/review",
    response_model=ReviewActionOut,
)
def review_extracted_field(
    document_id: int,
    payload: ReviewFieldIn,
    db: Session = Depends(get_db),
) -> ReviewActionOut:
    return apply_review(db, document_id, payload)


@router.get("/review-actions", response_model=ReviewActionListOut)
def read_review_actions(
    document_id: int | None = None,
    db: Session = Depends(get_db),
) -> ReviewActionListOut:
    return list_review_actions(db, document_id=document_id)


@router.get("/documents/{document_id}/review-actions", response_model=ReviewActionListOut)
def read_document_review_actions(
    document_id: int,
    db: Session = Depends(get_db),
) -> ReviewActionListOut:
    get_document(db, document_id)
    return list_review_actions(db, document_id=document_id)


@router.get("/export.json")
def export_json(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(export_payload(db))


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)) -> Response:
    payload = export_payload(db)
    lines = [
        "document_id,filename,status,field_name,value,verification_status,review_status,source_paragraph_ids"
    ]
    for item in payload["documents"]:
        document = item["document"]
        extraction = item.get("extraction") or {}
        fields = extraction.get("fields") or []
        if not fields:
            lines.append(
                ",".join(
                    [
                        str(document["id"]),
                        _csv(document["filename"]),
                        _csv(document["status"]),
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
            )
            continue
        for field in fields:
            lines.append(
                ",".join(
                    [
                        str(document["id"]),
                        _csv(document["filename"]),
                        _csv(document["status"]),
                        _csv(field.get("field_name")),
                        _csv(field.get("value")),
                        _csv(field.get("verification_status")),
                        _csv(field.get("review_status")),
                        _csv(field.get("source_paragraph_ids")),
                    ]
                )
            )
    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/csv")


def _csv(value) -> str:
    text = "" if value is None else str(value)
    return '"' + text.replace('"', '""') + '"'
