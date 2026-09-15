from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Document
from app.db.session import get_db
from app.schemas.audit import AuditFindingListOut, AuditFindingOut, AuditRunOut
from app.services.audit.pipeline import list_findings, run_audit

router = APIRouter(tags=["audit"])


@router.post("/audit/run", response_model=AuditRunOut)
def trigger_audit(db: Session = Depends(get_db)) -> AuditRunOut:
    count = run_audit(db)
    return AuditRunOut(finding_count=count)


@router.get("/findings/{finding_id}", response_model=AuditFindingOut)
def read_finding(finding_id: int, db: Session = Depends(get_db)):
    from app.db.models import AuditFinding
    from app.services.audit.pipeline import _to_out

    row = db.get(AuditFinding, finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _to_out(row)


@router.get("/findings", response_model=AuditFindingListOut)
def read_findings(db: Session = Depends(get_db)) -> AuditFindingListOut:
    return list_findings(db)


@router.get("/documents/{document_id}/findings", response_model=AuditFindingListOut)
def read_document_findings(
    document_id: int, db: Session = Depends(get_db)
) -> AuditFindingListOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return list_findings(db, document_id=document_id)
