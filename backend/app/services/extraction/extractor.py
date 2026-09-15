from typing import Any

from app.config import get_settings
from app.llm.base import LLMProvider, StructuredLLMResult
from app.prompts.loader import load_prompt
from app.schemas.extraction import InvoiceExtraction, PurchaseOrderExtraction
from app.services.extraction.classifier import format_paragraphs_for_prompt
from app.services.extraction.currency import verify_currency
from app.services.extraction.verification import (
    FieldVerification,
    apply_amount_validations,
    flatten_line_items,
    verify_cited_number,
    verify_cited_string,
)
from app.services.ocr.repository import ParagraphWithId

INVOICE_STRING_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "po_number",
)
INVOICE_NUMBER_FIELDS = ("subtotal", "tax", "total")
PURCHASE_ORDER_STRING_FIELDS = ("po_number", "vendor_name", "order_date")
PURCHASE_ORDER_NUMBER_FIELDS = ("total",)


async def extract_invoice(
    provider: LLMProvider,
    paragraphs: list[ParagraphWithId],
) -> StructuredLLMResult[InvoiceExtraction]:
    prompt = load_prompt("extract_invoice.txt") + "\n\n" + format_paragraphs_for_prompt(paragraphs)
    return await provider.generate_structured(
        prompt=prompt,
        response_schema=InvoiceExtraction,
    )


async def extract_purchase_order(
    provider: LLMProvider,
    paragraphs: list[ParagraphWithId],
) -> StructuredLLMResult[PurchaseOrderExtraction]:
    prompt = (
        load_prompt("extract_purchase_order.txt")
        + "\n\n"
        + format_paragraphs_for_prompt(paragraphs)
    )
    return await provider.generate_structured(
        prompt=prompt,
        response_schema=PurchaseOrderExtraction,
    )


def verify_invoice_extraction(
    extracted: InvoiceExtraction,
    paragraphs: list[ParagraphWithId],
    document_id: int,
) -> list[FieldVerification]:
    settings = get_settings()
    paragraphs_by_id = {paragraph.stable_id: paragraph for paragraph in paragraphs}
    fields: list[FieldVerification] = []

    for name in INVOICE_STRING_FIELDS:
        fields.append(
            verify_cited_string(
                name,
                getattr(extracted, name),
                paragraphs_by_id,
                document_id,
                settings.citation_match_threshold,
            )
        )
    for name in INVOICE_NUMBER_FIELDS:
        fields.append(
            verify_cited_number(
                name,
                getattr(extracted, name),
                paragraphs_by_id,
                document_id,
                settings.citation_match_threshold,
            )
        )
    fields.extend(
        verify_currency(
            extracted.currency,
            paragraphs_by_id,
            document_id,
            settings.citation_match_threshold,
        )
    )
    fields.extend(
        flatten_line_items(
            extracted.line_items,
            paragraphs_by_id,
            document_id,
            settings.citation_match_threshold,
            settings.amount_tolerance,
        )
    )
    return apply_amount_validations(fields, settings.amount_tolerance)


def verify_purchase_order_extraction(
    extracted: PurchaseOrderExtraction,
    paragraphs: list[ParagraphWithId],
    document_id: int,
) -> list[FieldVerification]:
    settings = get_settings()
    paragraphs_by_id = {paragraph.stable_id: paragraph for paragraph in paragraphs}
    fields: list[FieldVerification] = []

    for name in PURCHASE_ORDER_STRING_FIELDS:
        fields.append(
            verify_cited_string(
                name,
                getattr(extracted, name),
                paragraphs_by_id,
                document_id,
                settings.citation_match_threshold,
            )
        )
    for name in PURCHASE_ORDER_NUMBER_FIELDS:
        fields.append(
            verify_cited_number(
                name,
                getattr(extracted, name),
                paragraphs_by_id,
                document_id,
                settings.citation_match_threshold,
            )
        )
    fields.extend(
        flatten_line_items(
            extracted.line_items,
            paragraphs_by_id,
            document_id,
            settings.citation_match_threshold,
            settings.amount_tolerance,
        )
    )
    return apply_amount_validations(fields, settings.amount_tolerance)


def extraction_schema_for(document_type: str) -> type[Any] | None:
    if document_type == "invoice":
        return InvoiceExtraction
    if document_type == "purchase_order":
        return PurchaseOrderExtraction
    return None
