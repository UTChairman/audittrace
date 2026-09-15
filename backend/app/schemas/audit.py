from typing import Any, Literal

from pydantic import BaseModel, Field


class FieldCitation(BaseModel):
    document_id: int
    field_name: str
    value: Any | None = None
    source_paragraph_ids: list[str] = Field(default_factory=list)
    supporting_quote: str | None = None


class AuditFindingOut(BaseModel):
    id: int
    check_type: str
    severity: Literal["high", "medium", "low"]
    explanation: str
    document_id: int
    related_document_id: int | None
    field_citations: list[FieldCitation]
    created_at: str


class AuditFindingListOut(BaseModel):
    findings: list[AuditFindingOut]


class AuditRunOut(BaseModel):
    finding_count: int
