"""Synthetic evaluation cases: one planted example for each audit check."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LineSpec:
    description: str
    quantity: float
    unit_price: float
    amount: float
    detail: str | None = None


@dataclass(frozen=True)
class InvoiceSpec:
    filename: str
    vendor: str
    invoice_number: str
    invoice_date: str
    po_number: str
    line_items: tuple[LineSpec, ...]
    subtotal: float
    tax: float | None
    total: float
    address: str = "18 Harbour Street, Melbourne VIC 3000, Australia"
    role: str = "audit"


@dataclass(frozen=True)
class PurchaseOrderSpec:
    filename: str
    vendor: str
    po_number: str
    order_date: str
    line_items: tuple[LineSpec, ...]
    total: float
    bill_to: str = "Northbridge Studio\nAccounts Payable\nMelbourne VIC 3000"
    role: str = "audit"


@dataclass(frozen=True)
class CopySpec:
    filename: str
    source: str
    role: str = "audit"


@dataclass(frozen=True)
class DegradedSpec:
    filename: str
    source: str
    kind: str
    role: str = "extraction_only"


@dataclass(frozen=True)
class PlantedFinding:
    check_type: str
    documents: tuple[str, ...]
    severity: str | None = None


WEB = LineSpec("Web Design", 1, 85.0, 85.0, "Campaign landing page")
WIDGET = LineSpec("Widget assembly", 2, 50.0, 100.0)

INVOICES: tuple[InvoiceSpec, ...] = (
    InvoiceSpec(
        filename="inv_clean.pdf",
        vendor="Northbridge Studio",
        invoice_number="INV-1001",
        invoice_date="March 12, 2026",
        po_number="PO-1001",
        line_items=(WEB,),
        subtotal=85.0,
        tax=8.5,
        total=93.5,
    ),
    InvoiceSpec(
        filename="inv_vendor.pdf",
        vendor="Globex Design Co",
        invoice_number="INV-1002",
        invoice_date="March 12, 2026",
        po_number="PO-1002",
        line_items=(WEB,),
        subtotal=85.0,
        tax=8.5,
        total=93.5,
    ),
    InvoiceSpec(
        filename="inv_total_high.pdf",
        vendor="Northbridge Studio",
        invoice_number="INV-1003",
        invoice_date="March 12, 2026",
        po_number="PO-1003",
        line_items=(WEB,),
        subtotal=85.0,
        tax=8.5,
        total=93.5,
    ),
    InvoiceSpec(
        filename="inv_total_med.pdf",
        vendor="Northbridge Studio",
        invoice_number="INV-1004",
        invoice_date="March 12, 2026",
        po_number="PO-1004",
        line_items=(WEB,),
        subtotal=85.0,
        tax=8.5,
        total=93.5,
    ),
    InvoiceSpec(
        filename="inv_lines.pdf",
        vendor="Northbridge Studio",
        invoice_number="INV-1005",
        invoice_date="March 12, 2026",
        po_number="PO-1005",
        line_items=(WIDGET,),
        subtotal=100.0,
        tax=10.0,
        total=110.0,
    ),
    InvoiceSpec(
        filename="inv_date.pdf",
        vendor="Northbridge Studio",
        invoice_number="INV-1006",
        invoice_date="March 1, 2026",
        po_number="PO-1006",
        line_items=(WEB,),
        subtotal=85.0,
        tax=8.5,
        total=93.5,
    ),
    InvoiceSpec(
        filename="inv_dup_a.pdf",
        vendor="Harbour Print Co",
        invoice_number="INV-2000",
        invoice_date="April 2, 2026",
        po_number="PO-8001",
        line_items=(WEB,),
        subtotal=85.0,
        tax=8.5,
        total=93.5,
    ),
    InvoiceSpec(
        filename="inv_dup_b.pdf",
        vendor="Harbour Print Co",
        invoice_number="INV-2000",
        invoice_date="April 3, 2026",
        po_number="PO-8002",
        line_items=(WEB,),
        subtotal=85.0,
        tax=8.5,
        total=93.5,
    ),
)

PURCHASE_ORDERS: tuple[PurchaseOrderSpec, ...] = (
    PurchaseOrderSpec(
        filename="po_clean.pdf",
        vendor="Northbridge Studio",
        po_number="PO-1001",
        order_date="March 10, 2026",
        line_items=(WEB,),
        total=93.5,
    ),
    PurchaseOrderSpec(
        filename="po_vendor.pdf",
        vendor="Sliced Design Studio",
        po_number="PO-1002",
        order_date="March 10, 2026",
        line_items=(WEB,),
        total=93.5,
    ),
    PurchaseOrderSpec(
        filename="po_total_high.pdf",
        vendor="Northbridge Studio",
        po_number="PO-1003",
        order_date="March 10, 2026",
        line_items=(LineSpec("Web Design", 1, 70.0, 70.0),),
        total=77.0,
    ),
    PurchaseOrderSpec(
        filename="po_total_med.pdf",
        vendor="Northbridge Studio",
        po_number="PO-1004",
        order_date="March 10, 2026",
        line_items=(LineSpec("Web Design", 1, 82.0, 82.0),),
        total=90.2,
    ),
    PurchaseOrderSpec(
        filename="po_lines.pdf",
        vendor="Northbridge Studio",
        po_number="PO-1005",
        order_date="March 10, 2026",
        line_items=(LineSpec("Widget assembly", 1, 40.0, 40.0),),
        total=40.0,
    ),
    PurchaseOrderSpec(
        filename="po_date.pdf",
        vendor="Northbridge Studio",
        po_number="PO-1006",
        order_date="March 10, 2026",
        line_items=(WEB,),
        total=93.5,
    ),
    PurchaseOrderSpec(
        filename="po_dup_a.pdf",
        vendor="Northbridge Studio",
        po_number="PO-2010",
        order_date="May 1, 2026",
        line_items=(WEB,),
        total=93.5,
    ),
    PurchaseOrderSpec(
        filename="po_dup_b.pdf",
        vendor="Northbridge Studio",
        po_number="PO-2010",
        order_date="May 2, 2026",
        line_items=(WEB,),
        total=93.5,
    ),
)

COPIES: tuple[CopySpec, ...] = (
    CopySpec(filename="inv_clean_copy.pdf", source="inv_clean.pdf"),
)

DEGRADED: tuple[DegradedSpec, ...] = (
    DegradedSpec(filename="inv_clean_rotated.png", source="inv_clean.pdf", kind="rotate"),
    DegradedSpec(filename="inv_clean_faded.png", source="inv_clean.pdf", kind="fade"),
)

PLANTED_FINDINGS: tuple[PlantedFinding, ...] = (
    PlantedFinding("vendor_mismatch", ("inv_vendor.pdf", "po_vendor.pdf"), "high"),
    PlantedFinding("total_mismatch", ("inv_total_high.pdf", "po_total_high.pdf"), "high"),
    PlantedFinding("total_mismatch", ("inv_total_med.pdf", "po_total_med.pdf"), "medium"),
    PlantedFinding("line_item_price_mismatch", ("inv_lines.pdf", "po_lines.pdf"), "medium"),
    PlantedFinding("line_item_quantity_mismatch", ("inv_lines.pdf", "po_lines.pdf"), "medium"),
    PlantedFinding("invoice_dated_before_po", ("inv_date.pdf", "po_date.pdf"), "medium"),
    PlantedFinding("duplicate_invoice_number", ("inv_dup_a.pdf", "inv_dup_b.pdf"), "high"),
    PlantedFinding("duplicate_po_number", ("po_dup_a.pdf", "po_dup_b.pdf"), "high"),
    PlantedFinding("duplicate_document", ("inv_clean.pdf", "inv_clean_copy.pdf"), "high"),
)

PLANTED_FLAGS: tuple[dict[str, str], ...] = (
    {
        "filename": "inv_clean.pdf",
        "field_name": "currency",
        "flag_prefix": "ambiguous_currency_symbol",
    },
)


def invoice_fields(spec: InvoiceSpec) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "vendor_name": spec.vendor,
        "invoice_number": spec.invoice_number,
        "invoice_date": spec.invoice_date,
        "po_number": spec.po_number,
        "subtotal": spec.subtotal,
        "tax": spec.tax,
        "total": spec.total,
        "currency": "$",
    }
    for index, item in enumerate(spec.line_items):
        fields[f"line_items[{index}].description"] = item.description
        fields[f"line_items[{index}].quantity"] = item.quantity
        fields[f"line_items[{index}].unit_price"] = item.unit_price
        fields[f"line_items[{index}].amount"] = item.amount
        fields[f"line_items[{index}].detail"] = item.detail
    return fields


def po_fields(spec: PurchaseOrderSpec) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "vendor_name": spec.vendor,
        "po_number": spec.po_number,
        "order_date": spec.order_date,
        "total": spec.total,
    }
    for index, item in enumerate(spec.line_items):
        fields[f"line_items[{index}].description"] = item.description
        fields[f"line_items[{index}].quantity"] = item.quantity
        fields[f"line_items[{index}].unit_price"] = item.unit_price
        fields[f"line_items[{index}].amount"] = item.amount
        fields[f"line_items[{index}].detail"] = item.detail
    return fields


def all_ground_truth() -> dict[str, dict[str, Any]]:
    truth: dict[str, dict[str, Any]] = {}
    for spec in INVOICES:
        truth[spec.filename] = {
            "document_type": "invoice",
            "role": spec.role,
            "fields": invoice_fields(spec),
        }
    for spec in PURCHASE_ORDERS:
        truth[spec.filename] = {
            "document_type": "purchase_order",
            "role": spec.role,
            "fields": po_fields(spec),
        }
    clean = truth["inv_clean.pdf"]
    truth["inv_clean_copy.pdf"] = {
        "document_type": "invoice",
        "role": "audit",
        "fields": dict(clean["fields"]),
    }
    for spec in DEGRADED:
        truth[spec.filename] = {
            "document_type": "invoice",
            "role": spec.role,
            "fields": dict(clean["fields"]),
        }
    return truth


def audit_filenames() -> set[str]:
    names = {spec.filename for spec in INVOICES}
    names.update(spec.filename for spec in PURCHASE_ORDERS)
    names.update(spec.filename for spec in COPIES)
    return names
