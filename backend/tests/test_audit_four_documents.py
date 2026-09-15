import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Base,
    Document,
    DocumentClassification,
    ExtractedField,
    Extraction,
)
from app.services.audit.checks import AuditCheckSettings
from app.services.audit.pipeline import (
    list_findings,
    load_extracted_documents,
    persist_findings,
    run_audit_checks,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_document(
    db: Session,
    *,
    filename: str,
    file_hash: str,
    duplicate_of_document_id: int | None = None,
) -> Document:
    document = Document(
        filename=filename,
        content_type="application/pdf",
        file_hash=file_hash,
        file_size_bytes=1,
        storage_path=filename,
        status="extracted",
        duplicate_of_document_id=duplicate_of_document_id,
    )
    db.add(document)
    db.flush()
    return document


def _add_extraction(
    db: Session,
    document: Document,
    document_type: str,
    schema_type: str,
    fields: dict[str, object],
) -> None:
    db.add(
        DocumentClassification(
            document_id=document.id,
            document_type=document_type,
            model="test-model",
        )
    )
    extraction = Extraction(
        document_id=document.id,
        schema_type=schema_type,
        raw_llm_response="{}",
        model="test-model",
    )
    db.add(extraction)
    db.flush()
    for name, value in fields.items():
        db.add(
            ExtractedField(
                extraction_id=extraction.id,
                field_name=name,
                value_json=json.dumps(value),
                source_paragraph_ids=json.dumps([f"doc{document.id}_p1_para1"]),
                supporting_quote=str(value),
                verification_status="verified",
                validation_flags="[]",
                confidence_score=0.9,
            )
        )


def test_four_document_audit_produces_expected_finding_set() -> None:
    db = _session()
    invoice_fields = {
        "vendor_name": "DEMO - Sliced Invoices",
        "invoice_number": "INV-3337",
        "invoice_date": "January 25, 2016",
        "po_number": "12345",
        "total": 93.50,
        "line_items[0].description": "Web Design",
        "line_items[0].quantity": 1,
        "line_items[0].unit_price": 85.0,
        "line_items[0].amount": 85.0,
    }
    duplicate_fields = {
        **invoice_fields,
        "line_items[0].description": "Web Design",
        "line_items[0].detail": "This is a sample description...",
    }
    mismatch_po_fields = {
        "vendor_name": "Sliced Design Studio",
        "po_number": "12345",
        "order_date": "January 28, 2016",
        "total": 82.50,
        "line_items[0].description": "Web Design",
        "line_items[0].quantity": 1,
        "line_items[0].unit_price": 75.0,
        "line_items[0].amount": 75.0,
    }
    matching_po_fields = {
        "vendor_name": "DEMO - Sliced Invoices",
        "po_number": "12345",
        "order_date": "January 20, 2016",
        "total": 93.50,
        "line_items[0].description": "Web Design",
        "line_items[0].quantity": 1,
        "line_items[0].unit_price": 85.0,
        "line_items[0].amount": 85.0,
    }

    invoice = _add_document(db, filename="invoice.pdf", file_hash="invoice-hash")
    duplicate = _add_document(
        db,
        filename="invoice.pdf",
        file_hash="invoice-hash",
        duplicate_of_document_id=invoice.id,
    )
    mismatch_po = _add_document(db, filename="po_mismatch.pdf", file_hash="mismatch-hash")
    matching_po = _add_document(db, filename="po_matching.pdf", file_hash="matching-hash")

    _add_extraction(db, invoice, "invoice", "invoice", invoice_fields)
    _add_extraction(db, duplicate, "invoice", "invoice", duplicate_fields)
    _add_extraction(db, mismatch_po, "purchase_order", "purchase_order", mismatch_po_fields)
    _add_extraction(db, matching_po, "purchase_order", "purchase_order", matching_po_fields)
    db.commit()

    documents = load_extracted_documents(db)
    assert [doc.document_id for doc in documents] == [
        invoice.id,
        duplicate.id,
        mismatch_po.id,
        matching_po.id,
    ]
    assert documents[1].duplicate_of_document_id == invoice.id

    drafts = run_audit_checks(documents, settings=AuditCheckSettings())
    persist_findings(db, drafts)
    listed = list_findings(db)
    actual = {
        (finding.check_type, finding.document_id, finding.related_document_id)
        for finding in listed.findings
    }
    expected = {
        ("duplicate_document", invoice.id, duplicate.id),
        ("duplicate_po_number", mismatch_po.id, matching_po.id),
        ("vendor_mismatch", invoice.id, mismatch_po.id),
        ("total_mismatch", invoice.id, mismatch_po.id),
        ("line_item_price_mismatch", invoice.id, mismatch_po.id),
        ("invoice_dated_before_po", invoice.id, mismatch_po.id),
    }
    assert actual == expected
    assert len(listed.findings) == 6
    assert "duplicate_invoice_number" not in {item[0] for item in actual}
    assert not any(finding.document_id == duplicate.id for finding in listed.findings)
