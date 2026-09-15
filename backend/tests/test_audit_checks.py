from app.services.audit.checks import (
    AuditCheckSettings,
    ExtractedDocument,
    FieldSnapshot,
    check_duplicate_invoice_numbers,
    check_duplicate_po_numbers,
    check_invoice_against_po,
    invoice_before_po_severity,
    run_audit_checks,
    total_mismatch_severity,
)

SETTINGS = AuditCheckSettings()


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
        settings=SETTINGS,
    )
    assert findings == []


def test_vendor_mismatch() -> None:
    findings = check_invoice_against_po(
        _invoice(vendor_name=_field("vendor_name", "Globex Corp")),
        _purchase_order(),
        settings=SETTINGS,
    )
    assert any(finding.check_type == "vendor_mismatch" for finding in findings)
    finding = next(item for item in findings if item.check_type == "vendor_mismatch")
    assert finding.severity == "high"
    assert "Vendor on" in finding.explanation
    assert "Vendoron" not in finding.explanation
    assert "match vendor" in finding.explanation
    assert finding.field_citations[0]["field_name"] == "vendor_name"
    assert finding.field_citations[1]["document_id"] == 2


def test_total_mismatch_beyond_tolerance() -> None:
    findings = check_invoice_against_po(
        _invoice(total=_field("total", 150.0)),
        _purchase_order(),
        settings=SETTINGS,
    )
    finding = next(item for item in findings if item.check_type == "total_mismatch")
    assert finding.severity == "high"


def test_total_mismatch_at_or_below_five_percent_is_medium() -> None:
    findings = check_invoice_against_po(
        _invoice(total=_field("total", 110.0)),
        _purchase_order(total=_field("total", 108.0, paragraph="doc2_p1_para4")),
        settings=SETTINGS,
    )
    finding = next(item for item in findings if item.check_type == "total_mismatch")
    assert finding.severity == "medium"


def test_total_mismatch_high_percent_is_configurable() -> None:
    tight = AuditCheckSettings(total_mismatch_high_percent=1.0)
    findings = check_invoice_against_po(
        _invoice(total=_field("total", 110.0)),
        _purchase_order(),
        settings=tight,
    )
    finding = next(item for item in findings if item.check_type == "total_mismatch")
    assert finding.severity == "high"
    assert total_mismatch_severity(110.0, 108.0, 5.0) == "medium"
    assert total_mismatch_severity(113.4, 108.0, 5.0) == "medium"
    assert total_mismatch_severity(113.41, 108.0, 5.0) == "high"


def test_invoice_dated_before_po() -> None:
    findings = check_invoice_against_po(
        _invoice(invoice_date=_field("invoice_date", "December 1, 2015")),
        _purchase_order(),
        settings=SETTINGS,
    )
    finding = next(item for item in findings if item.check_type == "invoice_dated_before_po")
    assert finding.severity == "medium"


def test_invoice_dated_before_po_within_seven_days_is_low() -> None:
    findings = check_invoice_against_po(
        _invoice(invoice_date=_field("invoice_date", "January 25, 2016")),
        _purchase_order(order_date=_field("order_date", "January 28, 2016", paragraph="doc2_p1_para3")),
        settings=SETTINGS,
    )
    finding = next(item for item in findings if item.check_type == "invoice_dated_before_po")
    assert finding.severity == "low"
    assert invoice_before_po_severity(7, 7) == "low"
    assert invoice_before_po_severity(8, 7) == "medium"


def test_invoice_before_po_low_days_is_configurable() -> None:
    settings = AuditCheckSettings(invoice_before_po_low_days=2)
    findings = check_invoice_against_po(
        _invoice(invoice_date=_field("invoice_date", "January 25, 2016")),
        _purchase_order(order_date=_field("order_date", "January 28, 2016", paragraph="doc2_p1_para3")),
        settings=settings,
    )
    finding = next(item for item in findings if item.check_type == "invoice_dated_before_po")
    assert finding.severity == "medium"


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
        settings=SETTINGS,
    )
    by_type = {finding.check_type: finding for finding in findings}
    assert by_type["line_item_quantity_mismatch"].severity == "medium"
    assert by_type["line_item_price_mismatch"].severity == "medium"


def test_line_item_match_uses_token_set_ratio_on_normalized_descriptions() -> None:
    invoice = _invoice(
        **{
            "line_items[0].description": _field(
                "line_items[0].description",
                "Web Design - This is a sample description...",
            ),
            "line_items[0].unit_price": _field("line_items[0].unit_price", 85.0),
        }
    )
    purchase_order = _purchase_order(
        **{
            "line_items[0].description": _field(
                "line_items[0].description", "Web Design", paragraph="doc2_p1_para5"
            ),
            "line_items[0].unit_price": _field(
                "line_items[0].unit_price", 75.0, paragraph="doc2_p1_para7"
            ),
        }
    )
    findings = check_invoice_against_po(invoice, purchase_order, settings=SETTINGS)
    types = {finding.check_type for finding in findings}
    assert "line_item_not_on_po" not in types
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
    assert len(findings) == 1
    finding = findings[0]
    assert finding.check_type == "duplicate_invoice_number"
    assert finding.severity == "high"
    assert finding.document_id == 1
    assert finding.related_document_id == 3
    cited_ids = {citation["document_id"] for citation in finding.field_citations}
    assert cited_ids == {1, 3}


def test_run_audit_checks_links_by_po_number() -> None:
    findings = run_audit_checks(
        [_invoice(total=_field("total", 200.0)), _purchase_order()],
        settings=SETTINGS,
    )
    assert any(finding.check_type == "total_mismatch" for finding in findings)


def test_duplicate_po_number_cites_every_po_and_still_compares() -> None:
    matching_po = _purchase_order()
    mismatching_po = ExtractedDocument(
        document_id=4,
        filename="po-duplicate.pdf",
        document_type="purchase_order",
        fields={
            "vendor_name": _field(
                "vendor_name", "Globex Corp", paragraph="doc4_p1_para1"
            ),
            "po_number": _field("po_number", "PO-55", paragraph="doc4_p1_para2"),
            "order_date": _field(
                "order_date", "January 1, 2016", paragraph="doc4_p1_para3"
            ),
            "total": _field("total", 108.0, paragraph="doc4_p1_para4"),
            "line_items[0].description": _field(
                "line_items[0].description", "Widgets", paragraph="doc4_p1_para5"
            ),
            "line_items[0].quantity": _field(
                "line_items[0].quantity", 2, paragraph="doc4_p1_para6"
            ),
            "line_items[0].unit_price": _field(
                "line_items[0].unit_price", 50.0, paragraph="doc4_p1_para7"
            ),
            "line_items[0].amount": _field(
                "line_items[0].amount", 100.0, paragraph="doc4_p1_para8"
            ),
        },
    )
    findings = run_audit_checks(
        [_invoice(), matching_po, mismatching_po],
        settings=SETTINGS,
    )
    duplicates = [item for item in findings if item.check_type == "duplicate_po_number"]
    assert len(duplicates) == 1
    duplicate = duplicates[0]
    assert duplicate.severity == "high"
    cited_ids = {citation["document_id"] for citation in duplicate.field_citations}
    assert cited_ids == {2, 4}
    assert all(citation["field_name"] == "po_number" for citation in duplicate.field_citations)
    vendor_findings = [item for item in findings if item.check_type == "vendor_mismatch"]
    assert any(item.related_document_id == 4 for item in vendor_findings)
    assert check_duplicate_po_numbers([_invoice(), matching_po]) == []

