from app.schemas.extraction import CitedNumber, CitedString, LineItemExtraction
from app.services.extraction.verification import (
    FieldVerification,
    apply_amount_validations,
    compute_confidence_score,
    flatten_line_items,
    verify_cited_field,
)
from app.services.ocr.repository import ParagraphWithId
from app.utils.hashing import parse_stable_id


def _paragraph(stable_id: str, text: str, confidence: float = 0.9) -> ParagraphWithId:
    parsed = parse_stable_id(stable_id)
    return ParagraphWithId(
        stable_id=stable_id,
        page_number=parsed.page_number,
        page_paragraph_index=parsed.paragraph_index,
        text=text,
        confidence=confidence,
    )


def test_verified_when_quote_is_in_cited_paragraph() -> None:
    paragraph = _paragraph("doc1_p1_para1", "Invoice Number INV-1001")
    result = verify_cited_field(
        field_name="invoice_number",
        value="INV-1001",
        source_paragraph_ids=["doc1_p1_para1"],
        supporting_quote="INV-1001",
        paragraphs_by_id={paragraph.stable_id: paragraph},
        document_id=1,
        match_threshold=85,
    )
    assert result.verification_status == "verified"
    assert result.validation_flags == []
    assert result.confidence_score > 0.8


def test_unverified_when_quote_does_not_match() -> None:
    paragraph = _paragraph("doc1_p1_para1", "Invoice Number INV-1001")
    result = verify_cited_field(
        field_name="invoice_number",
        value="PO-9000",
        source_paragraph_ids=["doc1_p1_para1"],
        supporting_quote="Purchase Order PO-9000",
        paragraphs_by_id={paragraph.stable_id: paragraph},
        document_id=1,
        match_threshold=85,
    )
    assert result.verification_status == "unverified"
    assert any(
        flag.reason == "supporting_quote_not_found_in_cited_paragraphs"
        for flag in result.validation_flags
    )


def test_weak_when_quote_partially_matches() -> None:
    paragraph = _paragraph("doc1_p1_para1", "Vendor: Acme Supplies LLC")
    result = verify_cited_field(
        field_name="vendor_name",
        value="Acme Supplies",
        source_paragraph_ids=["doc1_p1_para1"],
        supporting_quote="Acme Corp",
        paragraphs_by_id={paragraph.stable_id: paragraph},
        document_id=1,
        match_threshold=85,
    )
    assert result.verification_status == "weak"
    assert any("citation_match_weak" in flag.reason for flag in result.validation_flags)


def test_unverified_for_missing_value() -> None:
    paragraph = _paragraph("doc1_p1_para1", "Invoice Number INV-1001")
    result = verify_cited_field(
        field_name="po_number",
        value=None,
        source_paragraph_ids=[],
        supporting_quote=None,
        paragraphs_by_id={paragraph.stable_id: paragraph},
        document_id=1,
        match_threshold=85,
    )
    assert result.verification_status == "unverified"
    assert result.confidence_score == 0.0


def test_invalid_paragraph_id_is_flagged() -> None:
    result = verify_cited_field(
        field_name="vendor_name",
        value="Acme",
        source_paragraph_ids=["not-an-id"],
        supporting_quote="Acme",
        paragraphs_by_id={},
        document_id=1,
        match_threshold=85,
    )
    assert result.verification_status == "unverified"
    assert any("cited_paragraph_id_invalid" in flag.reason for flag in result.validation_flags)


def test_wrong_document_id_in_citation_is_flagged() -> None:
    paragraph = _paragraph("doc2_p1_para1", "Acme")
    result = verify_cited_field(
        field_name="vendor_name",
        value="Acme",
        source_paragraph_ids=["doc2_p1_para1"],
        supporting_quote="Acme",
        paragraphs_by_id={paragraph.stable_id: paragraph},
        document_id=1,
        match_threshold=85,
    )
    assert result.verification_status == "unverified"
    assert any(
        "cited_paragraph_id_wrong_document" in flag.reason
        for flag in result.validation_flags
    )


def test_line_item_amount_mismatch_is_flagged() -> None:
    paragraph = _paragraph("doc1_p1_para2", "Widgets 2 x 10.00 = 25.00")
    paragraphs = {paragraph.stable_id: paragraph}
    cited = CitedNumber(
        value=10.0,
        source_paragraph_ids=["doc1_p1_para2"],
        supporting_quote="10.00",
    )
    items = [
        LineItemExtraction(
            description=CitedString(
                value="Widgets",
                source_paragraph_ids=["doc1_p1_para2"],
                supporting_quote="Widgets",
            ),
            quantity=CitedNumber(
                value=2,
                source_paragraph_ids=["doc1_p1_para2"],
                supporting_quote="2",
            ),
            unit_price=cited,
            amount=CitedNumber(
                value=25.0,
                source_paragraph_ids=["doc1_p1_para2"],
                supporting_quote="25.00",
            ),
        )
    ]
    fields = flatten_line_items(items, paragraphs, 1, 85, 0.01)
    amount = next(field for field in fields if field.field_name == "line_items[0].amount")
    assert any("line_item_amount_mismatch" in flag.reason for flag in amount.validation_flags)


def test_flatten_line_items_includes_optional_detail() -> None:
    paragraph = _paragraph(
        "doc1_p1_para2",
        "Web Design - This is a sample description 1 x 85.00",
    )
    paragraphs = {paragraph.stable_id: paragraph}
    items = [
        LineItemExtraction(
            description=CitedString(
                value="Web Design",
                source_paragraph_ids=["doc1_p1_para2"],
                supporting_quote="Web Design",
            ),
            detail=CitedString(
                value="This is a sample description",
                source_paragraph_ids=["doc1_p1_para2"],
                supporting_quote="This is a sample description",
            ),
            quantity=CitedNumber(
                value=1,
                source_paragraph_ids=["doc1_p1_para2"],
                supporting_quote="1",
            ),
            unit_price=CitedNumber(
                value=85.0,
                source_paragraph_ids=["doc1_p1_para2"],
                supporting_quote="85.00",
            ),
            amount=CitedNumber(
                value=85.0,
                source_paragraph_ids=["doc1_p1_para2"],
                supporting_quote="85.00",
            ),
        )
    ]
    fields = flatten_line_items(items, paragraphs, 1, 85, 0.01)
    names = [field.field_name for field in fields]
    assert "line_items[0].description" in names
    assert "line_items[0].detail" in names
    detail = next(field for field in fields if field.field_name == "line_items[0].detail")
    assert detail.value == "This is a sample description"


def test_line_items_sum_and_tax_total_validation() -> None:
    fields = [
        FieldVerification(
            field_name="subtotal",
            value=100.0,
            source_paragraph_ids=["doc1_p1_para1"],
            supporting_quote="100.00",
            verification_status="verified",
            validation_flags=[],
            confidence_score=0.9,
            ocr_confidence=0.9,
        ),
        FieldVerification(
            field_name="tax",
            value=8.0,
            source_paragraph_ids=["doc1_p1_para2"],
            supporting_quote="8.00",
            verification_status="verified",
            validation_flags=[],
            confidence_score=0.9,
            ocr_confidence=0.9,
        ),
        FieldVerification(
            field_name="total",
            value=120.0,
            source_paragraph_ids=["doc1_p1_para3"],
            supporting_quote="120.00",
            verification_status="verified",
            validation_flags=[],
            confidence_score=0.9,
            ocr_confidence=0.9,
        ),
        FieldVerification(
            field_name="line_items[0].amount",
            value=90.0,
            source_paragraph_ids=["doc1_p1_para4"],
            supporting_quote="90.00",
            verification_status="verified",
            validation_flags=[],
            confidence_score=0.9,
            ocr_confidence=0.9,
        ),
    ]
    result = apply_amount_validations(fields, 0.01)
    by_name = {field.field_name: field for field in result}
    assert any("line_items_sum_mismatch" in flag.reason for flag in by_name["subtotal"].validation_flags)
    assert any("total_mismatch" in flag.reason for flag in by_name["total"].validation_flags)


def test_matching_totals_have_no_amount_flags() -> None:
    fields = [
        FieldVerification(
            field_name="subtotal",
            value=100.0,
            source_paragraph_ids=["doc1_p1_para1"],
            supporting_quote="100.00",
            verification_status="verified",
            validation_flags=[],
            confidence_score=0.9,
            ocr_confidence=0.9,
        ),
        FieldVerification(
            field_name="tax",
            value=8.0,
            source_paragraph_ids=["doc1_p1_para2"],
            supporting_quote="8.00",
            verification_status="verified",
            validation_flags=[],
            confidence_score=0.9,
            ocr_confidence=0.9,
        ),
        FieldVerification(
            field_name="total",
            value=108.0,
            source_paragraph_ids=["doc1_p1_para3"],
            supporting_quote="108.00",
            verification_status="verified",
            validation_flags=[],
            confidence_score=0.9,
            ocr_confidence=0.9,
        ),
        FieldVerification(
            field_name="line_items[0].amount",
            value=100.0,
            source_paragraph_ids=["doc1_p1_para4"],
            supporting_quote="100.00",
            verification_status="verified",
            validation_flags=[],
            confidence_score=0.9,
            ocr_confidence=0.9,
        ),
    ]
    result = apply_amount_validations(fields, 0.01)
    assert all(not field.validation_flags for field in result)


def test_confidence_drops_when_validation_fails() -> None:
    verified = compute_confidence_score(
        value=100,
        verification_status="verified",
        ocr_confidence=1.0,
        has_validation_flags=False,
    )
    flagged = compute_confidence_score(
        value=100,
        verification_status="verified",
        ocr_confidence=1.0,
        has_validation_flags=True,
    )
    assert flagged < verified
