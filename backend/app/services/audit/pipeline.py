import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    AuditFinding,
    Document,
    DocumentClassification,
    ExtractedField,
    Extraction,
    SessionLocal,
)
from app.schemas.audit import AuditFindingListOut, AuditFindingOut, FieldCitation
from app.services.audit.checks import (
    ExtractedDocument,
    FieldSnapshot,
    FindingDraft,
    AuditCheckSettings,
    run_audit_checks,
)

logger = logging.getLogger(__name__)


def _latest_extraction(db: Session, document_id: int) -> Extraction | None:
    return (
        db.query(Extraction)
        .filter(Extraction.document_id == document_id)
        .order_by(Extraction.created_at.desc(), Extraction.id.desc())
        .first()
    )


def load_extracted_documents(db: Session) -> list[ExtractedDocument]:
    documents = (
        db.query(Document)
        .filter(Document.status == "extracted")
        .order_by(Document.id.asc())
        .all()
    )
    loaded: list[ExtractedDocument] = []
    for document in documents:
        classification = (
            db.query(DocumentClassification)
            .filter(DocumentClassification.document_id == document.id)
            .first()
        )
        if classification is None or classification.document_type == "unknown":
            continue
        extraction = _latest_extraction(db, document.id)
        if extraction is None:
            continue
        rows = (
            db.query(ExtractedField)
            .filter(ExtractedField.extraction_id == extraction.id)
            .all()
        )
        fields: dict[str, FieldSnapshot] = {}
        for row in rows:
            value = json.loads(row.value_json) if row.value_json is not None else None
            fields[row.field_name] = FieldSnapshot(
                field_name=row.field_name,
                value=value,
                source_paragraph_ids=json.loads(row.source_paragraph_ids),
                supporting_quote=row.supporting_quote,
            )
        loaded.append(
            ExtractedDocument(
                document_id=document.id,
                filename=document.filename,
                document_type=classification.document_type,
                fields=fields,
            )
        )
    return loaded


def persist_findings(db: Session, drafts: list[FindingDraft]) -> int:
    deleted = db.query(AuditFinding).delete(synchronize_session="fetch")
    db.flush()
    logger.info("Cleared %s previous audit finding(s) before recompute", deleted)
    now = datetime.now(timezone.utc)
    for draft in drafts:
        db.add(
            AuditFinding(
                check_type=draft.check_type,
                severity=draft.severity,
                explanation=draft.explanation,
                document_id=draft.document_id,
                related_document_id=draft.related_document_id,
                field_citations=json.dumps(draft.field_citations),
                created_at=now,
            )
        )
    db.commit()
    return len(drafts)


def run_audit(db: Session) -> int:
    settings = get_settings()
    documents = load_extracted_documents(db)
    drafts = run_audit_checks(
        documents,
        settings=AuditCheckSettings(
            amount_tolerance=settings.amount_tolerance,
            vendor_match_threshold=settings.vendor_match_threshold,
            line_item_match_threshold=settings.line_item_match_threshold,
            total_mismatch_high_percent=settings.total_mismatch_high_percent,
            invoice_before_po_low_days=settings.invoice_before_po_low_days,
        ),
    )
    count = persist_findings(db, drafts)
    logger.info("Audit complete: %s finding(s) across %s document(s)", count, len(documents))
    return count


def run_audit_standalone() -> int:
    db = SessionLocal()
    try:
        return run_audit(db)
    finally:
        db.close()


def _to_out(row: AuditFinding) -> AuditFindingOut:
    citations = [
        FieldCitation.model_validate(item) for item in json.loads(row.field_citations)
    ]
    created = row.created_at.isoformat() if row.created_at else ""
    return AuditFindingOut(
        id=row.id,
        check_type=row.check_type,
        severity=row.severity,  # type: ignore[arg-type]
        explanation=row.explanation,
        document_id=row.document_id,
        related_document_id=row.related_document_id,
        field_citations=citations,
        created_at=created,
    )


def list_findings(db: Session, document_id: int | None = None) -> AuditFindingListOut:
    query = db.query(AuditFinding)
    rows = query.all()
    if document_id is not None:
        matched: list[AuditFinding] = []
        for row in rows:
            if row.document_id == document_id or row.related_document_id == document_id:
                matched.append(row)
                continue
            citations = json.loads(row.field_citations or "[]")
            if any(item.get("document_id") == document_id for item in citations):
                matched.append(row)
        rows = matched
    severity_order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda row: (severity_order.get(row.severity, 9), row.id))
    return AuditFindingListOut(findings=[_to_out(row) for row in rows])
