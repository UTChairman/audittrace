import json
from pathlib import Path

import pytest
from fastapi import HTTPException
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
    kinds = [item.action for item in actions.actions]
    assert "edit" in kinds
    assert "recalculate_findings" in kinds
    assert json.loads(field.original_ai_value or "") == "Acme"
    assert json.loads(field.edited_value or "") == "Acme Supplies"
    assert json.loads(field.value_json or "") == "Acme Supplies"


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
    with pytest.raises(HTTPException) as raised:
        review_service.page_image_response(db, document.id, 1)
    assert raised.value.status_code in {400, 404}
    assert db.query(ReviewAction).count() == 0


def _review_fixture(
    db: Session,
    *,
    field_name: str = "invoice_number",
    value: object = "12345",
    review_status: str = "pending",
    filename: str = "invoice.pdf",
) -> tuple[Document, ExtractedField]:
    document = Document(
        filename=filename,
        content_type="application/pdf",
        file_hash=filename,
        file_size_bytes=1,
        storage_path=filename,
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
    encoded = json.dumps(value)
    field = ExtractedField(
        extraction_id=extraction.id,
        field_name=field_name,
        value_json=encoded,
        source_paragraph_ids="[]",
        supporting_quote=str(value),
        verification_status="verified",
        validation_flags="[]",
        confidence_score=0.9,
        review_status=review_status,
        original_ai_value=encoded,
    )
    db.add(field)
    db.commit()
    return document, field


def test_noop_edit_is_rejected() -> None:
    db = _session()
    document, field = _review_fixture(db, value="12345")
    with pytest.raises(HTTPException) as raised:
        apply_review(
            db,
            document.id,
            ReviewFieldIn(field_name="invoice_number", action="edit", value="12345"),
        )
    assert raised.value.status_code == 400
    assert "does not change" in raised.value.detail
    db.refresh(field)
    assert field.review_status == "pending"
    assert db.query(ReviewAction).count() == 0


def test_numeric_noop_edit_is_rejected() -> None:
    db = _session()
    document, _field = _review_fixture(db, field_name="tax", value=8.5)
    with pytest.raises(HTTPException) as raised:
        apply_review(
            db,
            document.id,
            ReviewFieldIn(field_name="tax", action="edit", value="8.50"),
        )
    assert raised.value.status_code == 400
    assert db.query(ReviewAction).count() == 0


def test_repeated_approve_and_reject_do_not_log() -> None:
    db = _session()
    document, field = _review_fixture(db)
    first = apply_review(
        db, document.id, ReviewFieldIn(field_name="invoice_number", action="approve")
    )
    assert first.previous_value == "pending"
    assert first.new_value == "approved"
    with pytest.raises(HTTPException) as raised:
        apply_review(
            db, document.id, ReviewFieldIn(field_name="invoice_number", action="approve")
        )
    assert raised.value.status_code == 409
    assert "already approved" in raised.value.detail
    apply_review(
        db, document.id, ReviewFieldIn(field_name="invoice_number", action="reject")
    )
    with pytest.raises(HTTPException) as raised:
        apply_review(
            db, document.id, ReviewFieldIn(field_name="invoice_number", action="reject")
        )
    assert raised.value.status_code == 409
    db.refresh(field)
    assert field.review_status == "rejected"
    actions = [row.action for row in db.query(ReviewAction).all()]
    assert actions == ["approve", "reject"]


def test_reset_restores_original_ai_value_and_logs() -> None:
    db = _session()
    document, field = _review_fixture(db, field_name="invoice_number", value="12345")
    apply_review(
        db,
        document.id,
        ReviewFieldIn(field_name="invoice_number", action="edit", value="99999"),
    )
    db.refresh(field)
    assert json.loads(field.value_json or "") == "99999"
    result = apply_review(
        db, document.id, ReviewFieldIn(field_name="invoice_number", action="reset")
    )
    db.refresh(field)
    assert result.action == "reset"
    assert result.previous_value == "99999"
    assert result.new_value == "12345"
    assert field.review_status == "pending"
    assert json.loads(field.value_json or "") == "12345"
    assert field.edited_value is None
    kinds = [item.action for item in list_review_actions(db, document.id).actions]
    assert kinds.count("reset") == 1


def test_review_log_includes_filename_and_approve_status_change() -> None:
    db = _session()
    document, _field = _review_fixture(db, filename="po_matching.pdf")
    result = apply_review(
        db, document.id, ReviewFieldIn(field_name="invoice_number", action="approve")
    )
    assert result.filename == "po_matching.pdf"
    listed = list_review_actions(db).actions
    assert listed[0].filename == "po_matching.pdf"
    assert listed[0].previous_value == "pending"
    assert listed[0].new_value == "approved"

