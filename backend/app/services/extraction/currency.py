import re
from typing import Literal

from app.schemas.extraction import CitedCurrency, ValidationFlag
from app.services.extraction.verification import (
    FieldVerification,
    compute_confidence_score,
    verify_cited_field,
)
from app.services.ocr.repository import ParagraphWithId

ISO_4217_CODES = frozenset(
    {
        "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
        "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
        "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
        "COP", "CRC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD", "EGP",
        "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP", "GMD",
        "GNF", "GTQ", "GYD", "HKD", "HNL", "HRK", "HTG", "HUF", "IDR", "ILS",
        "INR", "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR",
        "KMF", "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD", "LSL",
        "LYD", "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR",
        "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK", "NPR",
        "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG", "QAR",
        "RON", "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK", "SGD",
        "SHP", "SLE", "SOS", "SRD", "SSP", "STN", "SVC", "SYP", "SZL", "THB",
        "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX",
        "USD", "UYU", "UZS", "VES", "VND", "VUV", "WST", "XAF", "XCD", "XOF",
        "XPF", "YER", "ZAR", "ZMW", "ZWL",
    }
)

UNAMBIGUOUS_SYMBOLS: dict[str, str] = {
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "₩": "KRW",
    "₪": "ILS",
    "₦": "NGN",
    "₡": "CRC",
    "₫": "VND",
    "₱": "PHP",
    "₲": "PYG",
    "₴": "UAH",
    "₵": "GHS",
    "R$": "BRL",
}

PREFIXED_DOLLARS: dict[str, str] = {
    "US$": "USD",
    "U$": "USD",
    "AU$": "AUD",
    "A$": "AUD",
    "CA$": "CAD",
    "C$": "CAD",
    "NZ$": "NZD",
    "HK$": "HKD",
    "S$": "SGD",
    "R$": "BRL",
}

AMBIGUOUS_CURRENCY_REASON = (
    "ambiguous_currency_symbol: '$' can mean USD, AUD, CAD, NZD, HKD, SGD, "
    "MXN, or other dollar currencies. An ISO 4217 code was not stated."
)

_ISO_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(ISO_4217_CODES)) + r")\b",
    re.IGNORECASE,
)
CurrencyKind = Literal["explicit_code", "unambiguous_symbol", "ambiguous_symbol", "unknown"]


def _evidence_text(
    cited: CitedCurrency,
    paragraphs_by_id: dict[str, ParagraphWithId],
) -> str:
    parts: list[str] = []
    if cited.supporting_quote:
        parts.append(cited.supporting_quote)
    for stable_id in cited.source_paragraph_ids:
        paragraph = paragraphs_by_id.get(stable_id)
        if paragraph is not None:
            parts.append(paragraph.text)
    return "\n".join(parts)


def _find_explicit_iso(text: str) -> str | None:
    match = _ISO_PATTERN.search(text)
    if match is None:
        return None
    return match.group(1).upper()


def _find_prefixed_dollar(text: str) -> str | None:
    upper = text.upper()
    for prefix in sorted(PREFIXED_DOLLARS, key=len, reverse=True):
        if prefix in upper:
            return PREFIXED_DOLLARS[prefix]
    return None


def _find_unambiguous_symbol(text: str) -> str | None:
    for symbol, code in UNAMBIGUOUS_SYMBOLS.items():
        if symbol in text:
            return code
    return None


def resolve_currency_value(evidence_text: str, llm_value: str | None) -> tuple[str | None, CurrencyKind]:
    """Decide the stored currency from document evidence, not LLM guesses."""
    explicit = _find_explicit_iso(evidence_text)
    if explicit:
        return explicit, "explicit_code"

    prefixed = _find_prefixed_dollar(evidence_text)
    if prefixed:
        return prefixed, "unambiguous_symbol"

    unambiguous = _find_unambiguous_symbol(evidence_text)
    if unambiguous:
        return unambiguous, "unambiguous_symbol"

    if "$" in evidence_text or (
        llm_value is not None and llm_value.strip() in {"$", "dollar", "dollars", "Dollar", "Dollars"}
    ):
        return "$", "ambiguous_symbol"

    if llm_value:
        stripped = llm_value.strip()
        upper = stripped.upper()
        if upper in ISO_4217_CODES:
            return upper, "explicit_code"
        if stripped in UNAMBIGUOUS_SYMBOLS:
            return UNAMBIGUOUS_SYMBOLS[stripped], "unambiguous_symbol"
        if stripped == "$":
            return "$", "ambiguous_symbol"

    return (llm_value.strip() if llm_value else None), "unknown"


def verify_currency(
    cited: CitedCurrency,
    paragraphs_by_id: dict[str, ParagraphWithId],
    document_id: int,
    match_threshold: float,
) -> list[FieldVerification]:
    evidence = _evidence_text(cited, paragraphs_by_id)
    resolved, kind = resolve_currency_value(evidence, cited.value)

    result = verify_cited_field(
        field_name="currency",
        value=resolved,
        source_paragraph_ids=cited.source_paragraph_ids,
        supporting_quote=cited.supporting_quote,
        paragraphs_by_id=paragraphs_by_id,
        document_id=document_id,
        match_threshold=match_threshold,
    )
    result.value = resolved

    if resolved is None:
        return [result]

    if kind == "ambiguous_symbol":
        result.verification_status = "weak"
        result.validation_flags.append(
            ValidationFlag(reason=AMBIGUOUS_CURRENCY_REASON, severity="medium")
        )
        result.confidence_score = compute_confidence_score(
            value=resolved,
            verification_status="weak",
            ocr_confidence=result.ocr_confidence,
            has_validation_flags=True,
        )
    elif kind in {"explicit_code", "unambiguous_symbol"} and result.verification_status == "unverified":
        quote = cited.supporting_quote or ""
        symbol_ok = kind == "unambiguous_symbol" and bool(quote) and (
            _find_unambiguous_symbol(quote) == resolved
            or _find_prefixed_dollar(quote) == resolved
            or (resolved == "EUR" and "€" in quote)
            or (resolved == "GBP" and "£" in quote)
        )
        code_in_quote = bool(quote) and resolved.lower() in quote.lower()
        if symbol_ok or code_in_quote or (
            evidence and (
                resolved.lower() in evidence.lower()
                or _find_unambiguous_symbol(evidence) == resolved
            )
        ):
            if cited.source_paragraph_ids:
                result.verification_status = "verified"
                result.confidence_score = compute_confidence_score(
                    value=resolved,
                    verification_status="verified",
                    ocr_confidence=result.ocr_confidence,
                    has_validation_flags=False,
                )

    fields = [result]
    if cited.suggested_value:
        suggestion = verify_cited_field(
            field_name="currency_suggested",
            value=cited.suggested_value.strip().upper()
            if cited.suggested_value.strip().upper() in ISO_4217_CODES
            else cited.suggested_value,
            source_paragraph_ids=cited.suggested_source_paragraph_ids,
            supporting_quote=cited.suggested_quote,
            paragraphs_by_id=paragraphs_by_id,
            document_id=document_id,
            match_threshold=match_threshold,
        )
        suggestion.verification_status = "unverified"
        suggestion.validation_flags.append(
            ValidationFlag(
                reason=(
                    "suggested_currency is inferred from context and is never "
                    "treated as verified"
                ),
                severity="low",
            )
        )
        suggestion.confidence_score = compute_confidence_score(
            value=suggestion.value,
            verification_status="unverified",
            ocr_confidence=suggestion.ocr_confidence,
            has_validation_flags=True,
        )
        fields.append(suggestion)
    return fields
