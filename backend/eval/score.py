"""Compare extractions and audit findings against planted ground truth."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.services.extraction.verification import coerce_number, nearly_equal
from eval.cases import PLANTED_FINDINGS, PLANTED_FLAGS, audit_filenames, all_ground_truth

FIELD_TYPE_RE = re.compile(r"^line_items\[\d+\]\.(.+)$")


def field_type(field_name: str) -> str:
    match = FIELD_TYPE_RE.match(field_name)
    if match:
        return f"line_items.{match.group(1)}"
    return field_name


def normalize_text(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())


def values_match(field_name: str, expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if field_name.endswith("quantity") or field_name in {
        "total",
        "subtotal",
        "tax",
        "line_items.unit_price",
        "line_items.amount",
    } or field_name.endswith("unit_price") or field_name.endswith("amount"):
        left = coerce_number(expected)
        right = coerce_number(actual)
        if left is None or right is None:
            return False
        return nearly_equal(left, right, 0.05)
    return normalize_text(expected) == normalize_text(actual)


def document_filenames(db) -> dict[int, str]:
    from app.db.models import Document

    return {row.id: row.filename for row in db.query(Document).all()}


def extraction_fields(db, document_id: int) -> dict[str, dict[str, Any]]:
    from app.services.extraction.pipeline import get_latest_extraction

    try:
        extraction = get_latest_extraction(db, document_id)
    except LookupError:
        return {}
    return {field.field_name: field.model_dump() for field in extraction.fields}


def score_fields(db) -> dict[str, Any]:
    from app.db.models import Document

    truth = all_ground_truth()
    by_type: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    verified = 0
    cited = 0
    rows = []
    for document in db.query(Document).order_by(Document.id.asc()).all():
        expected_doc = truth.get(document.filename)
        if expected_doc is None:
            continue
        actual = extraction_fields(db, document.id)
        for name, expected_value in expected_doc["fields"].items():
            kind = field_type(name)
            by_type[kind]["total"] += 1
            actual_field = actual.get(name) or {}
            actual_value = actual_field.get("value")
            ok = values_match(name, expected_value, actual_value)
            if ok:
                by_type[kind]["correct"] += 1
            rows.append(
                {
                    "filename": document.filename,
                    "field_name": name,
                    "ok": ok,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )
            if expected_value is not None:
                cited += 1
                if actual_field.get("verification_status") == "verified":
                    verified += 1
    return {
        "by_type": dict(by_type),
        "citation_verified": verified,
        "citation_total": cited,
        "rows": rows,
    }


def finding_identity(check_type: str, filenames: set[str], severity: str | None) -> tuple:
    extra = severity if check_type == "total_mismatch" else None
    return (check_type, frozenset(filenames), extra)


def score_findings(db) -> dict[str, Any]:
    from app.services.audit.pipeline import list_findings

    names = document_filenames(db)
    audit_names = audit_filenames()
    actual_keys = []
    actual_rows = []
    for finding in list_findings(db).findings:
        involved = {names.get(finding.document_id, "")}
        if finding.related_document_id:
            involved.add(names.get(finding.related_document_id, ""))
        for citation in finding.field_citations:
            involved.add(names.get(citation.document_id, ""))
        involved.discard("")
        if not involved.issubset(audit_names):
            continue
        key = finding_identity(finding.check_type, involved, finding.severity)
        actual_keys.append(key)
        actual_rows.append(
            {
                "check_type": finding.check_type,
                "severity": finding.severity,
                "documents": sorted(involved),
                "explanation": finding.explanation,
            }
        )

    planted_keys = [
        finding_identity(item.check_type, set(item.documents), item.severity)
        for item in PLANTED_FINDINGS
    ]
    actual_set = set(actual_keys)
    planted_set = set(planted_keys)
    caught = []
    missed = []
    for item, key in zip(PLANTED_FINDINGS, planted_keys):
        entry = {
            "check_type": item.check_type,
            "severity": item.severity,
            "documents": list(item.documents),
        }
        if key in actual_set:
            caught.append(entry)
        else:
            missed.append(entry)
    extras = []
    for row, key in zip(actual_rows, actual_keys):
        if key not in planted_set:
            extras.append(row)
    return {
        "planted": len(PLANTED_FINDINGS),
        "caught": caught,
        "missed": missed,
        "false_positives": extras,
        "actual": actual_rows,
    }


def score_currency_flags(db) -> dict[str, Any]:
    from app.db.models import Document

    results = []
    for planted in PLANTED_FLAGS:
        document = (
            db.query(Document).filter(Document.filename == planted["filename"]).first()
        )
        ok = False
        if document is not None:
            fields = extraction_fields(db, document.id)
            field = fields.get(planted["field_name"]) or {}
            flags = field.get("validation_flags") or []
            ok = any(
                str(flag.get("reason", "")).startswith(planted["flag_prefix"])
                for flag in flags
            )
        results.append({**planted, "caught": ok})
    return {"flags": results}


def score_document_models(db, requested_model: str | None = None) -> dict[str, Any]:
    from app.db.models import Document, DocumentClassification, Extraction

    rows = []
    for document in db.query(Document).order_by(Document.id.asc()).all():
        extraction = (
            db.query(Extraction)
            .filter(Extraction.document_id == document.id)
            .order_by(Extraction.created_at.desc(), Extraction.id.desc())
            .first()
        )
        classification = (
            db.query(DocumentClassification)
            .filter(DocumentClassification.document_id == document.id)
            .first()
        )
        model = None
        if extraction is not None:
            model = extraction.model
        elif classification is not None:
            model = classification.model
        rows.append(
            {
                "filename": document.filename,
                "status": document.status,
                "model": model,
            }
        )
    return {"requested": requested_model, "rows": rows}


def render_markdown(
    field_score: dict[str, Any],
    finding_score: dict[str, Any],
    flag_score: dict[str, Any],
    model_score: dict[str, Any] | None = None,
) -> str:
    lines = [
        "## Evaluation summary",
        "",
    ]
    if model_score:
        requested = model_score.get("requested") or "—"
        lines.extend(
            [
                f"Pinned model: **{requested}** (no fallback).",
                "",
                "### Models used",
                "",
                "| Document | Status | Model |",
                "| --- | --- | --- |",
            ]
        )
        for row in model_score.get("rows") or []:
            lines.append(
                f"| {row['filename']} | {row['status']} | {row.get('model') or '—'} |"
            )
        lines.extend(["", "### Field accuracy", ""])
    else:
        lines.extend(["### Field accuracy", ""])
    lines.extend(
        [
            "| Field type | Correct | Total | Accuracy |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name in sorted(field_score["by_type"]):
        stats = field_score["by_type"][name]
        total = stats["total"] or 1
        pct = 100.0 * stats["correct"] / stats["total"] if stats["total"] else 0.0
        lines.append(f"| {name} | {stats['correct']} | {stats['total']} | {pct:.0f}% |")
    cite_total = field_score["citation_total"] or 1
    cite_pct = 100.0 * field_score["citation_verified"] / cite_total if field_score["citation_total"] else 0.0
    lines.extend(
        [
            "",
            f"Citation verification rate: **{field_score['citation_verified']}/{field_score['citation_total']}** ({cite_pct:.0f}%).",
            "",
            "### Planted findings",
            "",
            "| Check | Documents | Severity | Caught |",
            "| --- | --- | --- | --- |",
        ]
    )
    caught_keys = {
        finding_identity(item["check_type"], set(item["documents"]), item.get("severity"))
        for item in finding_score["caught"]
    }
    for item in PLANTED_FINDINGS:
        key = finding_identity(item.check_type, set(item.documents), item.severity)
        mark = "yes" if key in caught_keys else "no"
        lines.append(
            f"| {item.check_type} | {', '.join(item.documents)} | {item.severity or '—'} | {mark} |"
        )
    fp = len(finding_score["false_positives"])
    fn = len(finding_score["missed"])
    lines.extend(
        [
            "",
            f"False positives: **{fp}**. False negatives: **{fn}**.",
            "",
            "### Planted field flags",
            "",
            "| Document | Field | Flag | Caught |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in flag_score["flags"]:
        lines.append(
            f"| {item['filename']} | {item['field_name']} | {item['flag_prefix']} | {'yes' if item['caught'] else 'no'} |"
        )
    lines.append("")
    return "\n".join(lines)
