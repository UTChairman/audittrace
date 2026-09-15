import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Document, ExtractedField, Extraction, ReviewAction
from app.schemas.review import ReviewFieldIn
from app.services.review import apply_review, list_review_actions
from app.services.upload import list_documents


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_apply_review_edit_preserves_original_ai_value() -> None:
    db = _session()
    document = Document(
        filename="invoice.pdf",
        content_type="application/pdf",
        file_hash="abc",
        file_size_bytes=1,
        storage_path="invoice.pdf",
        status="extracted",
    )
    db.add(document)
    db.flush()
    extraction = Extraction(
        document_id=document.id,
        schema_type="invoice",
        raw_llm_response="{}",
        model="test",
    )
    db.add(extraction)
    db.flush()
    field = ExtractedField(
        extraction_id=extraction.id,
        field_name="vendor_name",
        value_json=json.dumps("Acme"),
        source_paragraph_ids="[]",
        supporting_quote="Acme",
        verification_status="verified",
        validation_flags="[]",
        confidence_score=0.9,
        review_status="pending",
    )
    db.add(field)
    db.commit()

    result = apply_review(
        db,
        document.id,
        ReviewFieldIn(field_name="vendor_name", action="edit", value="Acme Supplies"),
    )
    db.refresh(field)
    assert result.action == "edit"
    assert field.review_status == "edited"
    assert json.loads(field.original_ai_value or "") == "Acme"
    assert json.loads(field.edited_value or "") == "Acme Supplies"
    assert json.loads(field.value_json or "") == "Acme Supplies"
    actions = list_review_actions(db, document_id=document.id)
    assert len(actions.actions) == 1
    assert actions.actions[0].field_name == "vendor_name"


def test_list_documents_returns_newest_first() -> None:
    db = _session()
    for name in ("a.pdf", "b.pdf"):
        db.add(
            Document(
                filename=name,
                content_type="application/pdf",
                file_hash=name,
                file_size_bytes=1,
                storage_path=name,
                status="pending",
            )
        )
    db.commit()
    documents = list_documents(db)
    assert [item.filename for item in documents] == ["b.pdf", "a.pdf"]


def test_page_image_rejects_paths_outside_data_dir(tmp_path: Path, monkeypatch) -> None:
    from app.services import review as review_service

    monkeypatch.setattr(review_service, "DATA_DIR", tmp_path)
    db = _session()
    document = Document(
        filename="invoice.pdf",
        content_type="application/pdf",
        file_hash="abc",
        file_size_bytes=1,
        storage_path="invoice.pdf",
        status="extracted",
    )
    db.add(document)
    db.flush()
    from app.db.models import DocumentPage

    outside = Path.cwd() / "not-allowed.png"
    db.add(
        DocumentPage(
            document_id=document.id,
            page_number=1,
            image_path=str(outside),
            width_px=10,
            height_px=10,
        )
    )
    db.commit()
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        review_service.page_image_response(db, document.id, 1)
    assert raised.value.status_code in {400, 404}
    assert db.query(ReviewAction).count() == 0
