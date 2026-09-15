from app.schemas.extraction import CitedCurrency
from app.services.extraction.currency import AMBIGUOUS_CURRENCY_REASON, verify_currency
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


def test_explicit_iso_code_is_verified_usd() -> None:
    paragraph = _paragraph("doc1_p1_para1", "Currency: USD")
    fields = verify_currency(
        CitedCurrency(
            value="USD",
            source_paragraph_ids=["doc1_p1_para1"],
            supporting_quote="USD",
        ),
        {paragraph.stable_id: paragraph},
        document_id=1,
        match_threshold=85,
    )
    currency = fields[0]
    assert currency.field_name == "currency"
    assert currency.value == "USD"
    assert currency.verification_status == "verified"
    assert not any("ambiguous_currency_symbol" in flag.reason for flag in currency.validation_flags)


def test_unambiguous_euro_symbol_maps_to_eur() -> None:
    paragraph = _paragraph("doc1_p1_para1", "Total €1,250.00")
    fields = verify_currency(
        CitedCurrency(
            value="€",
            source_paragraph_ids=["doc1_p1_para1"],
            supporting_quote="€",
        ),
        {paragraph.stable_id: paragraph},
        document_id=1,
        match_threshold=85,
    )
    currency = fields[0]
    assert currency.value == "EUR"
    assert currency.verification_status == "verified"
    assert not any("ambiguous_currency_symbol" in flag.reason for flag in currency.validation_flags)


def test_ambiguous_dollar_is_weak_and_keeps_symbol() -> None:
    paragraph = _paragraph("doc1_p1_para1", "Total $1,250.00")
    fields = verify_currency(
        CitedCurrency(
            value="USD",
            source_paragraph_ids=["doc1_p1_para1"],
            supporting_quote="$",
            suggested_value="AUD",
            suggested_source_paragraph_ids=["doc1_p1_para2"],
            suggested_quote="Commonwealth Bank of Australia",
        ),
        {
            "doc1_p1_para1": paragraph,
            "doc1_p1_para2": _paragraph(
                "doc1_p1_para2", "Please pay to Commonwealth Bank of Australia"
            ),
        },
        document_id=1,
        match_threshold=85,
    )
    currency = next(field for field in fields if field.field_name == "currency")
    assert currency.value == "$"
    assert currency.verification_status == "weak"
    assert any(flag.reason == AMBIGUOUS_CURRENCY_REASON for flag in currency.validation_flags)

    suggested = next(field for field in fields if field.field_name == "currency_suggested")
    assert suggested.value == "AUD"
    assert suggested.verification_status == "unverified"
