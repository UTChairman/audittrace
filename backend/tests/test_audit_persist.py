from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditFinding, Base, Document
from app.services.audit.checks import FindingDraft
from app.services.audit.pipeline import persist_findings


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _document(db: Session, filename: str) -> Document:
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
    return document


def _draft(document_id: int, check_type: str) -> FindingDraft:
    return FindingDraft(
        check_type=check_type,
        severity="high",
        explanation=f"{check_type} on document {document_id}",
        document_id=document_id,
        related_document_id=None,
        field_citations=[],
    )


def test_persist_findings_replaces_previous_rows() -> None:
    db = _session()
    first = _document(db, "invoice.pdf")
    second = _document(db, "po.pdf")

    persist_findings(db, [_draft(first.id, "vendor_mismatch")])
    assert db.query(AuditFinding).count() == 1

    persist_findings(
        db,
        [
            _draft(first.id, "total_mismatch"),
            _draft(second.id, "duplicate_po_number"),
        ],
    )
    rows = db.query(AuditFinding).all()
    assert len(rows) == 2
    types = {row.check_type for row in rows}
    assert types == {"total_mismatch", "duplicate_po_number"}
    assert "vendor_mismatch" not in types
