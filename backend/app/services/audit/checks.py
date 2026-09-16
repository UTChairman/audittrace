from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from dateutil import parser as date_parser
from rapidfuzz import fuzz

from app.services.extraction.verification import coerce_number, nearly_equal


@dataclass
class FieldSnapshot:
    field_name: str
    value: Any | None
    source_paragraph_ids: list[str] = field(default_factory=list)
    supporting_quote: str | None = None


@dataclass
class ExtractedDocument:
    document_id: int
    filename: str
    document_type: str
    fields: dict[str, FieldSnapshot]
    duplicate_of_document_id: int | None = None


@dataclass
class FindingDraft:
    check_type: str
    severity: str
    explanation: str
    document_id: int
    related_document_id: int | None
    field_citations: list[dict[str, Any]]


@dataclass(frozen=True)
class AuditCheckSettings:
    amount_tolerance: float = 0.01
    vendor_match_threshold: int = 85
    line_item_match_threshold: int = 80
    total_mismatch_high_percent: float = 5.0
    invoice_before_po_low_days: int = 7


def normalize_key(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def parse_document_date(value: Any | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date_parser.parse(text, fuzzy=True, dayfirst=False).date()
    except (ValueError, OverflowError, TypeError):
        return None


def document_currency(document: ExtractedDocument) -> str | None:
    for name in ("currency", "currency_suggested"):
        snapshot = document.fields.get(name)
        if snapshot is not None and snapshot.value not in (None, ""):
            return str(snapshot.value).strip()
    return None


def format_amount(value: float, currency: str | None = None) -> str:
    amount = f"{value:.2f}"
    if not currency:
        return amount
    token = currency.strip()
    if len(token) == 1:
        return f"{token}{amount}"
    return f"{token} {amount}"


def citation_for(document: ExtractedDocument, field_name: str) -> dict[str, Any]:
    snapshot = document.fields.get(field_name)
    if snapshot is None:
        return {
            "document_id": document.document_id,
            "field_name": field_name,
            "value": None,
            "source_paragraph_ids": [],
            "supporting_quote": None,
        }
    return {
        "document_id": document.document_id,
        "field_name": snapshot.field_name,
        "value": snapshot.value,
        "source_paragraph_ids": snapshot.source_paragraph_ids,
        "supporting_quote": snapshot.supporting_quote,
    }


def collect_line_items(document: ExtractedDocument) -> list[dict[str, FieldSnapshot | None]]:
    items: list[dict[str, FieldSnapshot | None]] = []
    index = 0
    while True:
        prefix = f"line_items[{index}]"
        keys = (
            f"{prefix}.description",
            f"{prefix}.quantity",
            f"{prefix}.unit_price",
            f"{prefix}.amount",
        )
        if not any(key in document.fields for key in keys):
            break
        items.append(
            {
                "description": document.fields.get(f"{prefix}.description"),
                "detail": document.fields.get(f"{prefix}.detail"),
                "quantity": document.fields.get(f"{prefix}.quantity"),
                "unit_price": document.fields.get(f"{prefix}.unit_price"),
                "amount": document.fields.get(f"{prefix}.amount"),
            }
        )
        index += 1
    return items


def _description_text(item: dict[str, FieldSnapshot | None]) -> str:
    snapshot = item.get("description")
    if snapshot is None or snapshot.value is None:
        return ""
    return str(snapshot.value)


def normalize_line_item_description(value: Any | None) -> str:
    if value is None:
        return ""
    text = str(value).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def match_line_items(
    invoice_items: list[dict[str, FieldSnapshot | None]],
    po_items: list[dict[str, FieldSnapshot | None]],
    threshold: int,
) -> list[tuple[int, int, float]]:
    """Greedy match of invoice line items to PO line items by description."""
    used_po: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    candidates: list[tuple[float, int, int]] = []
    for invoice_index, invoice_item in enumerate(invoice_items):
        invoice_text = normalize_line_item_description(_description_text(invoice_item))
        if not invoice_text:
            continue
        for po_index, po_item in enumerate(po_items):
            po_text = normalize_line_item_description(_description_text(po_item))
            if not po_text:
                continue
            score = float(fuzz.token_set_ratio(invoice_text, po_text))
            if score >= threshold:
                candidates.append((score, invoice_index, po_index))
    candidates.sort(reverse=True)
    matched_invoice: set[int] = set()
    for score, invoice_index, po_index in candidates:
        if invoice_index in matched_invoice or po_index in used_po:
            continue
        matched_invoice.add(invoice_index)
        used_po.add(po_index)
        matches.append((invoice_index, po_index, score))
    return matches


def _document_identity_citation(document: ExtractedDocument) -> dict[str, Any]:
    if "invoice_number" in document.fields:
        return citation_for(document, "invoice_number")
    if "po_number" in document.fields:
        return citation_for(document, "po_number")
    return {
        "document_id": document.document_id,
        "field_name": "filename",
        "value": document.filename,
        "source_paragraph_ids": [],
        "supporting_quote": None,
    }


def check_duplicate_documents(documents: list[ExtractedDocument]) -> list[FindingDraft]:
    by_id = {document.document_id: document for document in documents}
    copies_by_original: dict[int, list[ExtractedDocument]] = {}
    for document in documents:
        original_id = document.duplicate_of_document_id
        if original_id is None:
            continue
        copies_by_original.setdefault(original_id, []).append(document)

    findings: list[FindingDraft] = []
    for original_id, copies in copies_by_original.items():
        original = by_id.get(original_id)
        group = [original, *copies] if original is not None else copies
        names = ", ".join(document.filename for document in group)
        primary = original or copies[0]
        related = copies[0] if original is not None else (
            copies[1] if len(copies) > 1 else None
        )
        findings.append(
            FindingDraft(
                check_type="duplicate_document",
                severity="high",
                explanation=(
                    "The same file was uploaded more than once ({names}) "
                    "and may indicate a double payment risk."
                ).format(names=names),
                document_id=primary.document_id,
                related_document_id=related.document_id if related is not None else None,
                field_citations=[_document_identity_citation(document) for document in group],
            )
        )
    return findings


def check_duplicate_invoice_numbers(documents: list[ExtractedDocument]) -> list[FindingDraft]:
    invoices = [
        doc
        for doc in documents
        if doc.document_type == "invoice" and doc.duplicate_of_document_id is None
    ]
    grouped: dict[str, list[ExtractedDocument]] = {}
    for invoice in invoices:
        number = normalize_key(
            invoice.fields["invoice_number"].value
            if "invoice_number" in invoice.fields
            else None
        )
        if number is None:
            continue
        grouped.setdefault(number, []).append(invoice)

    findings: list[FindingDraft] = []
    for number, group in grouped.items():
        if len(group) < 2:
            continue
        names = ", ".join(invoice.filename for invoice in group)
        citations = [citation_for(invoice, "invoice_number") for invoice in group]
        findings.append(
            FindingDraft(
                check_type="duplicate_invoice_number",
                severity="high",
                explanation=(
                    f"Invoice number {number} appears on more than one document "
                    f"({names})."
                ),
                document_id=group[0].document_id,
                related_document_id=group[1].document_id,
                field_citations=citations,
            )
        )
    return findings


def check_duplicate_po_numbers(documents: list[ExtractedDocument]) -> list[FindingDraft]:
    purchase_orders = [
        doc
        for doc in documents
        if doc.document_type == "purchase_order" and doc.duplicate_of_document_id is None
    ]
    grouped: dict[str, list[ExtractedDocument]] = {}
    for purchase_order in purchase_orders:
        number = normalize_key(
            purchase_order.fields["po_number"].value
            if "po_number" in purchase_order.fields
            else None
        )
        if number is None:
            continue
        grouped.setdefault(number, []).append(purchase_order)

    findings: list[FindingDraft] = []
    for number, group in grouped.items():
        if len(group) < 2:
            continue
        citations = [citation_for(purchase_order, "po_number") for purchase_order in group]
        names = ", ".join(purchase_order.filename for purchase_order in group)
        findings.append(
            FindingDraft(
                check_type="duplicate_po_number",
                severity="high",
                explanation=(
                    f"Purchase order number {number} appears on more than one document "
                    f"({names}). Comparison checks still run against each PO."
                ),
                document_id=group[0].document_id,
                related_document_id=group[1].document_id,
                field_citations=citations,
            )
        )
    return findings


def total_mismatch_severity(
    invoice_total: float,
    po_total: float,
    high_percent: float,
) -> str:
    """High when the difference is above high_percent of the PO total; otherwise medium."""
    if po_total == 0:
        return "high" if invoice_total != 0 else "medium"
    percent = abs(invoice_total - po_total) / abs(po_total) * 100
    if percent > high_percent + 1e-9:
        return "high"
    return "medium"


def invoice_before_po_severity(gap_days: int, low_days: int) -> str:
    if gap_days <= low_days:
        return "low"
    return "medium"


def check_invoice_against_po(
    invoice: ExtractedDocument,
    purchase_order: ExtractedDocument,
    *,
    settings: AuditCheckSettings,
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    findings.extend(
        _vendor_mismatch(invoice, purchase_order, settings.vendor_match_threshold)
    )
    findings.extend(_total_mismatch(invoice, purchase_order, settings))
    findings.extend(_invoice_dated_before_po(invoice, purchase_order, settings))
    findings.extend(_line_item_differences(invoice, purchase_order, settings))
    return findings


def _vendor_mismatch(
    invoice: ExtractedDocument,
    purchase_order: ExtractedDocument,
    threshold: int,
) -> list[FindingDraft]:
    invoice_vendor = invoice.fields.get("vendor_name")
    po_vendor = purchase_order.fields.get("vendor_name")
    if invoice_vendor is None or po_vendor is None:
        return []
    if invoice_vendor.value is None or po_vendor.value is None:
        return []
    score = float(
        fuzz.token_sort_ratio(str(invoice_vendor.value), str(po_vendor.value))
    )
    if score >= threshold:
        return []
    return [
        FindingDraft(
            check_type="vendor_mismatch",
            severity="high",
            explanation=(
                "Vendor on invoice '{invoice_vendor}' does not match vendor on "
                "purchase order '{po_vendor}' (similarity {score})."
            ).format(
                invoice_vendor=invoice_vendor.value,
                po_vendor=po_vendor.value,
                score=f"{score:.0f}",
            ),
            document_id=invoice.document_id,
            related_document_id=purchase_order.document_id,
            field_citations=[
                citation_for(invoice, "vendor_name"),
                citation_for(purchase_order, "vendor_name"),
            ],
        )
    ]


def _total_mismatch(
    invoice: ExtractedDocument,
    purchase_order: ExtractedDocument,
    settings: AuditCheckSettings,
) -> list[FindingDraft]:
    invoice_total = coerce_number(
        invoice.fields["total"].value if "total" in invoice.fields else None
    )
    po_total = coerce_number(
        purchase_order.fields["total"].value if "total" in purchase_order.fields else None
    )
    if invoice_total is None or po_total is None:
        return []
    if nearly_equal(invoice_total, po_total, settings.amount_tolerance):
        return []
    percent = (
        0.0
        if po_total == 0
        else abs(invoice_total - po_total) / abs(po_total) * 100
    )
    severity = total_mismatch_severity(
        invoice_total, po_total, settings.total_mismatch_high_percent
    )
    return [
        FindingDraft(
            check_type="total_mismatch",
            severity=severity,
            explanation=(
                "Invoice total {invoice_total} differs from purchase order total "
                "{po_total} by {percent}% of the PO total."
            ).format(
                invoice_total=format_amount(
                    invoice_total, document_currency(invoice)
                ),
                po_total=format_amount(
                    po_total, document_currency(purchase_order)
                ),
                percent=f"{percent:.1f}",
            ),
            document_id=invoice.document_id,
            related_document_id=purchase_order.document_id,
            field_citations=[
                citation_for(invoice, "total"),
                citation_for(purchase_order, "total"),
            ],
        )
    ]


def _invoice_dated_before_po(
    invoice: ExtractedDocument,
    purchase_order: ExtractedDocument,
    settings: AuditCheckSettings,
) -> list[FindingDraft]:
    invoice_date = parse_document_date(
        invoice.fields["invoice_date"].value if "invoice_date" in invoice.fields else None
    )
    po_date = parse_document_date(
        purchase_order.fields["order_date"].value
        if "order_date" in purchase_order.fields
        else None
    )
    if invoice_date is None or po_date is None:
        return []
    if invoice_date >= po_date:
        return []
    gap_days = (po_date - invoice_date).days
    severity = invoice_before_po_severity(
        gap_days, settings.invoice_before_po_low_days
    )
    return [
        FindingDraft(
            check_type="invoice_dated_before_po",
            severity=severity,
            explanation=(
                "Invoice date {invoice_date} is {gap_days} {day_word} before "
                "purchase order date {po_date}."
            ).format(
                invoice_date=invoice_date.isoformat(),
                gap_days=gap_days,
                day_word="day" if gap_days == 1 else "days",
                po_date=po_date.isoformat(),
            ),
            document_id=invoice.document_id,
            related_document_id=purchase_order.document_id,
            field_citations=[
                citation_for(invoice, "invoice_date"),
                citation_for(purchase_order, "order_date"),
            ],
        )
    ]


def _line_item_differences(
    invoice: ExtractedDocument,
    purchase_order: ExtractedDocument,
    settings: AuditCheckSettings,
) -> list[FindingDraft]:
    invoice_items = collect_line_items(invoice)
    po_items = collect_line_items(purchase_order)
    if not invoice_items or not po_items:
        return []

    matches = match_line_items(
        invoice_items, po_items, settings.line_item_match_threshold
    )
    matched_invoice = {pair[0] for pair in matches}
    findings: list[FindingDraft] = []

    for invoice_index, po_index, _score in matches:
        invoice_item = invoice_items[invoice_index]
        po_item = po_items[po_index]
        invoice_qty = coerce_number(
            invoice_item["quantity"].value if invoice_item["quantity"] else None
        )
        po_qty = coerce_number(po_item["quantity"].value if po_item["quantity"] else None)
        if invoice_qty is not None and po_qty is not None and not nearly_equal(
            invoice_qty, po_qty, settings.amount_tolerance
        ):
            findings.append(
                FindingDraft(
                    check_type="line_item_quantity_mismatch",
                    severity="medium",
                    explanation=(
                        "Quantity for '{description}' is {invoice_qty} on the invoice "
                        "and {po_qty} on the purchase order."
                    ).format(
                        description=_description_text(invoice_item) or f"line {invoice_index}",
                        invoice_qty=invoice_qty,
                        po_qty=po_qty,
                    ),
                    document_id=invoice.document_id,
                    related_document_id=purchase_order.document_id,
                    field_citations=[
                        _line_citation(invoice, invoice_index, "quantity", invoice_item),
                        _line_citation(purchase_order, po_index, "quantity", po_item),
                    ],
                )
            )

        invoice_price = coerce_number(
            invoice_item["unit_price"].value if invoice_item["unit_price"] else None
        )
        po_price = coerce_number(
            po_item["unit_price"].value if po_item["unit_price"] else None
        )
        if invoice_price is not None and po_price is not None and not nearly_equal(
            invoice_price, po_price, settings.amount_tolerance
        ):
            findings.append(
                FindingDraft(
                    check_type="line_item_price_mismatch",
                    severity="medium",
                    explanation=(
                        "Unit price for '{description}' is {invoice_price} on the invoice "
                        "and {po_price} on the purchase order."
                    ).format(
                        description=_description_text(invoice_item) or f"line {invoice_index}",
                        invoice_price=format_amount(
                            invoice_price, document_currency(invoice)
                        ),
                        po_price=format_amount(
                            po_price, document_currency(purchase_order)
                        ),
                    ),
                    document_id=invoice.document_id,
                    related_document_id=purchase_order.document_id,
                    field_citations=[
                        _line_citation(invoice, invoice_index, "unit_price", invoice_item),
                        _line_citation(purchase_order, po_index, "unit_price", po_item),
                    ],
                )
            )

    for invoice_index, invoice_item in enumerate(invoice_items):
        if invoice_index in matched_invoice:
            continue
        description = _description_text(invoice_item) or f"line {invoice_index}"
        findings.append(
            FindingDraft(
                check_type="line_item_not_on_po",
                severity="medium",
                explanation=(
                    f"Invoice line '{description}' was not found on purchase order "
                    f"{purchase_order.filename}."
                ),
                document_id=invoice.document_id,
                related_document_id=purchase_order.document_id,
                field_citations=[
                    _line_citation(invoice, invoice_index, "description", invoice_item)
                ],
            )
        )
    return findings


def _line_citation(
    document: ExtractedDocument,
    index: int,
    attribute: str,
    item: dict[str, FieldSnapshot | None],
) -> dict[str, Any]:
    field_name = f"line_items[{index}].{attribute}"
    snapshot = item.get(attribute)
    if snapshot is None:
        return citation_for(document, field_name)
    return {
        "document_id": document.document_id,
        "field_name": field_name,
        "value": snapshot.value,
        "source_paragraph_ids": snapshot.source_paragraph_ids,
        "supporting_quote": snapshot.supporting_quote,
    }


def run_audit_checks(
    documents: list[ExtractedDocument],
    *,
    settings: AuditCheckSettings,
) -> list[FindingDraft]:
    findings = check_duplicate_documents(documents)
    findings.extend(check_duplicate_invoice_numbers(documents))
    findings.extend(check_duplicate_po_numbers(documents))
    comparable = [doc for doc in documents if doc.duplicate_of_document_id is None]
    invoices = [doc for doc in comparable if doc.document_type == "invoice"]
    purchase_orders = [
        doc for doc in comparable if doc.document_type == "purchase_order"
    ]
    pos_by_number: dict[str, list[ExtractedDocument]] = {}
    for purchase_order in purchase_orders:
        number = normalize_key(
            purchase_order.fields["po_number"].value
            if "po_number" in purchase_order.fields
            else None
        )
        if number is None:
            continue
        pos_by_number.setdefault(number, []).append(purchase_order)

    for invoice in invoices:
        po_number = normalize_key(
            invoice.fields["po_number"].value if "po_number" in invoice.fields else None
        )
        if po_number is None:
            continue
        for purchase_order in pos_by_number.get(po_number, []):
            findings.extend(
                check_invoice_against_po(
                    invoice,
                    purchase_order,
                    settings=settings,
                )
            )
    return findings
