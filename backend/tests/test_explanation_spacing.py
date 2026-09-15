import re

from app.services.audit.checks import (
    AuditCheckSettings,
    ExtractedDocument,
    FieldSnapshot,
    run_audit_checks,
)

SETTINGS = AuditCheckSettings()

# Hyphenated document identifiers such as INV-3337 are allowed.
_ID_TOKEN = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")
_LETTER_DIGIT = re.compile(r"[A-Za-z]\d")
_DIGIT_LETTER = re.compile(r"\d[A-Za-z]")
_PERCENT_THEN_WORD = re.compile(r"%[A-Za-z]")
_SIMILARITY_GLUED = re.compile(r"(?i)similarity\d")


def assert_explanation_spacing(explanation: str) -> None:
    """Fail if a number or percent sign is glued to a neighboring word."""
    assert _SIMILARITY_GLUED.search(explanation) is None, explanation
    assert _PERCENT_THEN_WORD.search(explanation) is None, explanation
    if "%" in explanation:
        assert re.search(r"%\s", explanation), explanation
    stripped = _ID_TOKEN.sub("", explanation)
    letter_digit = _LETTER_DIGIT.search(stripped)
    assert letter_digit is None, f"{explanation!r} has {letter_digit.group()!r}"
    digit_letter = _DIGIT_LETTER.search(stripped)
    assert digit_letter is None, f"{explanation!r} has {digit_letter.group()!r}"


def _field(name: str, value, paragraph: str = "doc1_p1_para1") -> FieldSnapshot:
    return FieldSnapshot(
        field_name=name,
        value=value,
        source_paragraph_ids=[paragraph],
        supporting_quote=str(value),
    )


def _invoice(document_id: int = 1, filename: str = "invoice.pdf", **overrides: object) -> ExtractedDocument:
    fields = {
        "vendor_name": _field("vendor_name", "DEMO - Sliced Invoices"),
        "invoice_number": _field("invoice_number", "INV-3337"),
        "invoice_date": _field("invoice_date", "January 25, 2016"),
        "po_number": _field("po_number", "12345"),
        "total": _field("total", 93.5),
        "line_items[0].description": _field("line_items[0].description", "Web Design"),
        "line_items[0].quantity": _field("line_items[0].quantity", 1),
        "line_items[0].unit_price": _field("line_items[0].unit_price", 85.0),
        "line_items[0].amount": _field("line_items[0].amount", 85.0),
        "line_items[1].description": _field("line_items[1].description", "Rush printing"),
        "line_items[1].quantity": _field("line_items[1].quantity", 1),
        "line_items[1].unit_price": _field("line_items[1].unit_price", 10.0),
        "line_items[1].amount": _field("line_items[1].amount", 10.0),
    }
    fields.update({key: value for key, value in overrides.items() if isinstance(value, FieldSnapshot)})
    return ExtractedDocument(
        document_id=document_id,
        filename=filename,
        document_type="invoice",
        fields=fields,
    )


def _purchase_order(
    document_id: int,
    filename: str,
    *,
    vendor: str,
    order_date: str,
    total: float,
    unit_price: float,
    description: str = "Web Design",
) -> ExtractedDocument:
    return ExtractedDocument(
        document_id=document_id,
        filename=filename,
        document_type="purchase_order",
        fields={
            "vendor_name": _field("vendor_name", vendor, paragraph=f"doc{document_id}_p1_para1"),
            "po_number": _field("po_number", "12345", paragraph=f"doc{document_id}_p1_para2"),
            "order_date": _field("order_date", order_date, paragraph=f"doc{document_id}_p1_para3"),
            "total": _field("total", total, paragraph=f"doc{document_id}_p1_para4"),
            "line_items[0].description": _field(
                "line_items[0].description", description, paragraph=f"doc{document_id}_p1_para5"
            ),
            "line_items[0].quantity": _field(
                "line_items[0].quantity", 2, paragraph=f"doc{document_id}_p1_para6"
            ),
            "line_items[0].unit_price": _field(
                "line_items[0].unit_price", unit_price, paragraph=f"doc{document_id}_p1_para7"
            ),
            "line_items[0].amount": _field(
                "line_items[0].amount", 100.0, paragraph=f"doc{document_id}_p1_para8"
            ),
        },
    )


def test_every_finding_explanation_has_spaces_around_numbers_and_percents() -> None:
    invoice = _invoice()
    duplicate = ExtractedDocument(
        document_id=2,
        filename="invoice-copy.pdf",
        document_type="invoice",
        fields=dict(invoice.fields),
        duplicate_of_document_id=1,
    )
    other_invoice = ExtractedDocument(
        document_id=5,
        filename="other-invoice.pdf",
        document_type="invoice",
        fields={
            "invoice_number": _field("invoice_number", "INV-3337", paragraph="doc5_p1_para1"),
            "po_number": _field("po_number", "99999", paragraph="doc5_p1_para2"),
        },
    )
    mismatch_po = _purchase_order(
        3,
        "po_mismatch.pdf",
        vendor="Sliced Design Studio",
        order_date="January 28, 2016",
        total=82.5,
        unit_price=75.0,
        description="Web Design",
    )
    matching_po = _purchase_order(
        4,
        "po_matching.pdf",
        vendor="DEMO - Sliced Invoices",
        order_date="January 20, 2016",
        total=93.5,
        unit_price=85.0,
    )

    findings = run_audit_checks(
        [invoice, duplicate, mismatch_po, matching_po, other_invoice],
        settings=SETTINGS,
    )
    types = {finding.check_type for finding in findings}
    expected = {
        "duplicate_document",
        "duplicate_invoice_number",
        "duplicate_po_number",
        "vendor_mismatch",
        "total_mismatch",
        "invoice_dated_before_po",
        "line_item_price_mismatch",
        "line_item_quantity_mismatch",
        "line_item_not_on_po",
    }
    assert expected <= types
    assert findings
    for finding in findings:
        assert_explanation_spacing(finding.explanation)

    vendor = next(item for item in findings if item.check_type == "vendor_mismatch")
    assert re.search(r"similarity \d+", vendor.explanation)
    assert "similarity48" not in vendor.explanation
    total = next(item for item in findings if item.check_type == "total_mismatch")
    assert "% of" in total.explanation
    assert "%of" not in total.explanation
