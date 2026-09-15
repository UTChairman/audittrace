from app.services.audit.checks import (
    ExtractedDocument,
    FieldSnapshot,
    check_duplicate_invoice_numbers,
    check_invoice_against_po,
    run_audit_checks,
)


def _field(name: str, value, quote: str | None = None, paragraph: str = "doc1_p1_para1") -> FieldSnapshot:
    return FieldSnapshot(
        field_name=name,
        value=value,
        source_paragraph_ids=[paragraph],
        supporting_quote=quote or str(value),
    )


def _invoice(**overrides: object) -> ExtractedDocument:
    fields = {
        "vendor_name": _field("vendor_name", "Acme Supplies"),
        "invoice_number": _field("invoice_number", "INV-1001"),
        "invoice_date": _field("invoice_date", "January 25, 2016"),
        "po_number": _field("po_number", "PO-55"),
        "total": _field("total", 108.0),
        "line_items[0].description": _field("line_items[0].description", "Widgets"),
        "line_items[0].quantity": _field("line_items[0].quantity", 2),
        "line_items[0].unit_price": _field("line_items[0].unit_price", 50.0),
        "line_items[0].amount": _field("line_items[0].amount", 100.0),
    }
    fields.update({key: value for key, value in overrides.items() if isinstance(value, FieldSnapshot)})
    return ExtractedDocument(
        document_id=1,
        filename="invoice.pdf",
        document_type="invoice",
        fields=fields,
    )


def _purchase_order(**overrides: object) -> ExtractedDocument:
    fields = {
        "vendor_name": _field("vendor_name", "Acme Supplies", paragraph="doc2_p1_para1"),
        "po_number": _field("po_number", "PO-55", paragraph="doc2_p1_para2"),
        "order_date": _field("order_date", "January 1, 2016", paragraph="doc2_p1_para3"),
        "total": _field("total", 108.0, paragraph="doc2_p1_para4"),
        "line_items[0].description": _field(
            "line_items[0].description", "Widgets", paragraph="doc2_p1_para5"
        ),
        "line_items[0].quantity": _field(
            "line_items[0].quantity", 2, paragraph="doc2_p1_para6"
        ),
        "line_items[0].unit_price": _field(
            "line_items[0].unit_price", 50.0, paragraph="doc2_p1_para7"
        ),
        "line_items[0].amount": _field(
            "line_items[0].amount", 100.0, paragraph="doc2_p1_para8"
        ),
    }
    fields.update({key: value for key, value in overrides.items() if isinstance(value, FieldSnapshot)})
    return ExtractedDocument(
        document_id=2,
        filename="po.pdf",
        document_type="purchase_order",
        fields=fields,
    )


def test_matching_invoice_and_po_have_no_findings() -> None:
    findings = check_invoice_against_po(
        _invoice(),
        _purchase_order(),
        amount_tolerance=0.01,
        vendor_match_threshold=85,
        line_item_match_threshold=80,
    )
    assert findings == []


def test_vendor_mismatch() -> None:
    findings = check_invoice_against_po(
        _invoice(vendor_name=_field("vendor_name", "Globex Corp")),
        _purchase_order(),
        amount_tolerance=0.01,
        vendor_match_threshold=85,
        line_item_match_threshold=80,
    )
    assert any(finding.check_type == "vendor_mismatch" for finding in findings)
    finding = next(item for item in findings if item.check_type == "vendor_mismatch")
    assert finding.severity == "high"
    assert finding.field_citations[0]["field_name"] == "vendor_name"
    assert finding.field_citations[1]["document_id"] == 2


def test_total_mismatch_beyond_tolerance() -> None:
    findings = check_invoice_against_po(
        _invoice(total=_field("total", 150.0)),
        _purchase_order(),
        amount_tolerance=0.01,
        vendor_match_threshold=85,
        line_item_match_threshold=80,
    )
    assert any(finding.check_type == "total_mismatch" for finding in findings)


def test_invoice_dated_before_po() -> None:
    findings = check_invoice_against_po(
        _invoice(invoice_date=_field("invoice_date", "December 1, 2015")),
        _purchase_order(),
        amount_tolerance=0.01,
        vendor_match_threshold=85,
        line_item_match_threshold=80,
    )
    assert any(finding.check_type == "invoice_dated_before_po" for finding in findings)


def test_line_item_quantity_and_price_mismatch() -> None:
    invoice = _invoice(
        **{
            "line_items[0].quantity": _field("line_items[0].quantity", 5),
            "line_items[0].unit_price": _field("line_items[0].unit_price", 60.0),
        }
    )
    findings = check_invoice_against_po(
        invoice,
        _purchase_order(),
        amount_tolerance=0.01,
        vendor_match_threshold=85,
        line_item_match_threshold=80,
    )
    types = {finding.check_type for finding in findings}
    assert "line_item_quantity_mismatch" in types
    assert "line_item_price_mismatch" in types


def test_duplicate_invoice_numbers() -> None:
    first = _invoice()
    second = ExtractedDocument(
        document_id=3,
        filename="invoice-copy.pdf",
        document_type="invoice",
        fields={
            "invoice_number": _field(
                "invoice_number", "INV-1001", paragraph="doc3_p1_para1"
            )
        },
    )
    findings = check_duplicate_invoice_numbers([first, second])
    assert len(findings) == 2
    assert all(finding.check_type == "duplicate_invoice_number" for finding in findings)


def test_run_audit_checks_links_by_po_number() -> None:
    findings = run_audit_checks(
        [_invoice(total=_field("total", 200.0)), _purchase_order()],
        amount_tolerance=0.01,
        vendor_match_threshold=85,
        line_item_match_threshold=80,
    )
    assert any(finding.check_type == "total_mismatch" for finding in findings)
