from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Literal

from rapidfuzz import fuzz

from app.schemas.extraction import CitedNumber, CitedString, LineItemExtraction, ValidationFlag
from app.services.ocr.repository import ParagraphWithId
from app.utils.hashing import parse_stable_id

VerificationStatus = Literal["verified", "weak", "unverified", "not_present"]
WEAK_MATCH_THRESHOLD = 50.0


@dataclass
class FieldVerification:
    field_name: str
    value: Any | None
    source_paragraph_ids: list[str]
    supporting_quote: str | None
    verification_status: VerificationStatus
    validation_flags: list[ValidationFlag] = field(default_factory=list)
    confidence_score: float = 0.0
    ocr_confidence: float | None = None


def coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("$", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def nearly_equal(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def _best_quote_score(quote: str, paragraph_texts: list[str]) -> float:
    if not quote or not paragraph_texts:
        return 0.0
    best = 0.0
    for text in paragraph_texts:
        if quote in text:
            return 100.0
        best = max(best, float(fuzz.partial_ratio(quote, text)))
    return best


def _ocr_confidence(paragraphs: list[ParagraphWithId]) -> float | None:
    values = [paragraph.confidence for paragraph in paragraphs if paragraph.confidence is not None]
    if not values:
        return None
    return float(mean(values))


def compute_confidence_score(
    *,
    value: Any | None,
    verification_status: VerificationStatus,
    ocr_confidence: float | None,
    has_validation_flags: bool,
) -> float:
    """Combine OCR confidence, citation status, and numeric validation."""
    if value is None or verification_status == "not_present":
        return 0.0
    citation_score = {"verified": 1.0, "weak": 0.5, "unverified": 0.0}[verification_status]
    ocr_score = 0.5 if ocr_confidence is None else max(0.0, min(ocr_confidence, 1.0))
    validation_score = 0.0 if has_validation_flags else 1.0
    return round((0.45 * citation_score) + (0.35 * ocr_score) + (0.20 * validation_score), 4)


def verify_cited_field(
    *,
    field_name: str,
    value: Any | None,
    source_paragraph_ids: list[str],
    supporting_quote: str | None,
    paragraphs_by_id: dict[str, ParagraphWithId],
    document_id: int,
    match_threshold: float,
) -> FieldVerification:
    if value is None:
        return FieldVerification(
            field_name=field_name,
            value=None,
            source_paragraph_ids=[],
            supporting_quote=None,
            verification_status="not_present",
            validation_flags=[],
            confidence_score=0.0,
            ocr_confidence=None,
        )

    flags: list[ValidationFlag] = []
    cited: list[ParagraphWithId] = []

    for stable_id in source_paragraph_ids:
        try:
            parsed = parse_stable_id(stable_id)
        except ValueError:
            flags.append(
                ValidationFlag(
                    reason=f"cited_paragraph_id_invalid: {stable_id}",
                    severity="high",
                )
            )
            continue
        if parsed.document_id != document_id:
            flags.append(
                ValidationFlag(
                    reason=f"cited_paragraph_id_wrong_document: {stable_id}",
                    severity="high",
                )
            )
            continue
        paragraph = paragraphs_by_id.get(stable_id)
        if paragraph is None:
            flags.append(
                ValidationFlag(
                    reason=f"cited_paragraph_not_found: {stable_id}",
                    severity="high",
                )
            )
            continue
        cited.append(paragraph)

    ocr_confidence = _ocr_confidence(cited)
    quote = supporting_quote.strip() if supporting_quote else None

    if not quote:
        flags.append(
            ValidationFlag(reason="missing_supporting_quote", severity="high")
        )
        status = "unverified"
    elif not cited:
        flags.append(
            ValidationFlag(
                reason="supporting_quote_not_found_in_cited_paragraphs",
                severity="high",
            )
        )
        status = "unverified"
    else:
        score = _best_quote_score(quote, [paragraph.text for paragraph in cited])
        if score >= match_threshold:
            status = "verified"
        elif score >= WEAK_MATCH_THRESHOLD:
            flags.append(
                ValidationFlag(
                    reason=f"citation_match_weak: score={score:.1f}",
                    severity="medium",
                )
            )
            status = "weak"
        else:
            flags.append(
                ValidationFlag(
                    reason="supporting_quote_not_found_in_cited_paragraphs",
                    severity="high",
                )
            )
            status = "unverified"

    if value is not None and not source_paragraph_ids:
        flags.append(
            ValidationFlag(reason="missing_source_paragraph_ids", severity="high")
        )
        status = "unverified"

    confidence = compute_confidence_score(
        value=value,
        verification_status=status,
        ocr_confidence=ocr_confidence,
        has_validation_flags=False,
    )
    return FieldVerification(
        field_name=field_name,
        value=value,
        source_paragraph_ids=source_paragraph_ids,
        supporting_quote=supporting_quote,
        verification_status=status,
        validation_flags=flags,
        confidence_score=confidence,
        ocr_confidence=ocr_confidence,
    )


def verify_cited_string(
    field_name: str,
    cited: CitedString,
    paragraphs_by_id: dict[str, ParagraphWithId],
    document_id: int,
    match_threshold: float,
) -> FieldVerification:
    return verify_cited_field(
        field_name=field_name,
        value=cited.value,
        source_paragraph_ids=cited.source_paragraph_ids,
        supporting_quote=cited.supporting_quote,
        paragraphs_by_id=paragraphs_by_id,
        document_id=document_id,
        match_threshold=match_threshold,
    )


def verify_cited_number(
    field_name: str,
    cited: CitedNumber,
    paragraphs_by_id: dict[str, ParagraphWithId],
    document_id: int,
    match_threshold: float,
) -> FieldVerification:
    return verify_cited_field(
        field_name=field_name,
        value=cited.value,
        source_paragraph_ids=cited.source_paragraph_ids,
        supporting_quote=cited.supporting_quote,
        paragraphs_by_id=paragraphs_by_id,
        document_id=document_id,
        match_threshold=match_threshold,
    )


def flatten_line_items(
    line_items: list[LineItemExtraction],
    paragraphs_by_id: dict[str, ParagraphWithId],
    document_id: int,
    match_threshold: float,
    amount_tolerance: float,
) -> list[FieldVerification]:
    fields: list[FieldVerification] = []
    for index, item in enumerate(line_items):
        prefix = f"line_items[{index}]"
        description = verify_cited_string(
            f"{prefix}.description",
            item.description,
            paragraphs_by_id,
            document_id,
            match_threshold,
        )
        detail = verify_cited_string(
            f"{prefix}.detail",
            item.detail,
            paragraphs_by_id,
            document_id,
            match_threshold,
        )
        quantity = verify_cited_number(
            f"{prefix}.quantity",
            item.quantity,
            paragraphs_by_id,
            document_id,
            match_threshold,
        )
        unit_price = verify_cited_number(
            f"{prefix}.unit_price",
            item.unit_price,
            paragraphs_by_id,
            document_id,
            match_threshold,
        )
        amount = verify_cited_number(
            f"{prefix}.amount",
            item.amount,
            paragraphs_by_id,
            document_id,
            match_threshold,
        )
        quantity_value = coerce_number(quantity.value)
        unit_price_value = coerce_number(unit_price.value)
        amount_value = coerce_number(amount.value)
        if (
            quantity_value is not None
            and unit_price_value is not None
            and amount_value is not None
        ):
            expected = quantity_value * unit_price_value
            if not nearly_equal(expected, amount_value, amount_tolerance):
                amount.validation_flags.append(
                    ValidationFlag(
                        reason=(
                            f"line_item_amount_mismatch: {quantity_value} * "
                            f"{unit_price_value} != {amount_value}"
                        ),
                        severity="high",
                    )
                )
                amount.confidence_score = compute_confidence_score(
                    value=amount.value,
                    verification_status=amount.verification_status,
                    ocr_confidence=amount.ocr_confidence,
                    has_validation_flags=True,
                )
        fields.extend([description, detail, quantity, unit_price, amount])
    return fields


def apply_amount_validations(
    fields: list[FieldVerification],
    amount_tolerance: float,
) -> list[FieldVerification]:
    by_name = {field.field_name: field for field in fields}

    line_amounts: list[float] = []
    index = 0
    while f"line_items[{index}].amount" in by_name:
        amount_value = coerce_number(by_name[f"line_items[{index}].amount"].value)
        if amount_value is not None:
            line_amounts.append(amount_value)
        index += 1

    subtotal = by_name.get("subtotal")
    if subtotal is not None and line_amounts:
        subtotal_value = coerce_number(subtotal.value)
        if subtotal_value is not None:
            items_sum = sum(line_amounts)
            if not nearly_equal(items_sum, subtotal_value, amount_tolerance):
                subtotal.validation_flags.append(
                    ValidationFlag(
                        reason=(
                            f"line_items_sum_mismatch: items sum to {items_sum} "
                            f"but subtotal is {subtotal_value}"
                        ),
                        severity="high",
                    )
                )
                subtotal.confidence_score = compute_confidence_score(
                    value=subtotal.value,
                    verification_status=subtotal.verification_status,
                    ocr_confidence=subtotal.ocr_confidence,
                    has_validation_flags=True,
                )

    total = by_name.get("total")
    tax = by_name.get("tax")
    if total is not None and subtotal is not None:
        total_value = coerce_number(total.value)
        subtotal_value = coerce_number(subtotal.value)
        tax_value = coerce_number(tax.value) if tax is not None else None
        if total_value is not None and subtotal_value is not None and tax_value is not None:
            expected_total = subtotal_value + tax_value
            if not nearly_equal(expected_total, total_value, amount_tolerance):
                total.validation_flags.append(
                    ValidationFlag(
                        reason=(
                            f"total_mismatch: subtotal {subtotal_value} + tax "
                            f"{tax_value} != total {total_value}"
                        ),
                        severity="high",
                    )
                )
                total.confidence_score = compute_confidence_score(
                    value=total.value,
                    verification_status=total.verification_status,
                    ocr_confidence=total.ocr_confidence,
                    has_validation_flags=True,
                )

    return fields
