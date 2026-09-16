from typing import Any, Literal

from pydantic import BaseModel, Field


class ReviewFieldIn(BaseModel):
    field_name: str
    action: Literal["approve", "reject", "edit", "reset"]
    value: Any | None = None
    note: str | None = None
    actor: str = "reviewer"


class ReviewActionOut(BaseModel):
    id: int
    document_id: int
    filename: str | None = None
    field_id: int | None
    field_name: str | None = None
    action: str
    actor: str
    previous_value: Any | None = None
    new_value: Any | None = None
    note: str | None = None
    created_at: str


class ReviewActionListOut(BaseModel):
    actions: list[ReviewActionOut]


class DocumentListOut(BaseModel):
    documents: list[Any] = Field(default_factory=list)
