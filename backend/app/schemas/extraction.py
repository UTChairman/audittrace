from typing import Any, Literal

from pydantic import BaseModel, Field


class CitedString(BaseModel):
    value: str | None = None
    source_paragraph_ids: list[str] = Field(default_factory=list)
    supporting_quote: str | None = None


class CitedNumber(BaseModel):
    value: float | None = None
    source_paragraph_ids: list[str] = Field(default_factory=list)
    supporting_quote: str | None = None


class CitedCurrency(BaseModel):
    value: str | None = None
    source_paragraph_ids: list[str] = Field(default_factory=list)
    supporting_quote: str | None = None
    suggested_value: str | None = None
    suggested_source_paragraph_ids: list[str] = Field(default_factory=list)
    suggested_quote: str | None = None


class LineItemExtraction(BaseModel):
    description: CitedString = Field(default_factory=CitedString)
    detail: CitedString = Field(default_factory=CitedString)
    quantity: CitedNumber = Field(default_factory=CitedNumber)
    unit_price: CitedNumber = Field(default_factory=CitedNumber)
    amount: CitedNumber = Field(default_factory=CitedNumber)


class InvoiceExtraction(BaseModel):
    vendor_name: CitedString = Field(default_factory=CitedString)
    invoice_number: CitedString = Field(default_factory=CitedString)
    invoice_date: CitedString = Field(default_factory=CitedString)
    po_number: CitedString = Field(default_factory=CitedString)
    line_items: list[LineItemExtraction] = Field(default_factory=list)
    subtotal: CitedNumber = Field(default_factory=CitedNumber)
    tax: CitedNumber = Field(default_factory=CitedNumber)
    total: CitedNumber = Field(default_factory=CitedNumber)
    currency: CitedCurrency = Field(default_factory=CitedCurrency)


class PurchaseOrderExtraction(BaseModel):
    po_number: CitedString = Field(default_factory=CitedString)
    vendor_name: CitedString = Field(default_factory=CitedString)
    order_date: CitedString = Field(default_factory=CitedString)
    line_items: list[LineItemExtraction] = Field(default_factory=list)
    total: CitedNumber = Field(default_factory=CitedNumber)


class DocumentClassificationResult(BaseModel):
    document_type: Literal["invoice", "purchase_order", "unknown"]
    reason: str


class ValidationFlag(BaseModel):
    reason: str
    severity: Literal["low", "medium", "high"]


class ExtractedFieldOut(BaseModel):
    field_name: str
    value: Any | None
    source_paragraph_ids: list[str]
    supporting_quote: str | None
    verification_status: Literal["verified", "weak", "unverified"]
    validation_flags: list[ValidationFlag]
    confidence_score: float
    review_status: str


class ExtractionOut(BaseModel):
    document_id: int
    status: str
    document_type: str | None
    schema_type: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    fields: list[ExtractedFieldOut]


class ExtractJobOut(BaseModel):
    document_id: int
    status: str


class PendingExtractOut(BaseModel):
    queued: int
    document_ids: list[int]
    delay_seconds: float

