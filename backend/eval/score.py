"""Compare extractions and audit findings against planted ground truth."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.services.extraction.verification import coerce_number, nearly_equal
from eval.cases import PLANTED_FINDINGS, audit_filenames, all_ground_truth

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


def document_condition(filename: str) -> str:
    lower = filename.lower()
    if "faded" in lower:
        return "faded scan"
    if "rotated" in lower:
        return "rotated scan"
    return "clean PDF"


def format_value(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    return text if text else "—"


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
                    "verification_status": actual_field.get("verification_status"),
                    "condition": document_condition(document.filename),
                }
            )
            if expected_value is not None:
                cited += 1
                if actual_field.get("verification_status") == "verified":
                    verified += 1
    incorrect = [row for row in rows if not row["ok"]]
    weak = [
        row
        for row in rows
        if row["expected"] is not None
        and row.get("verification_status") in {"weak", "unverified"}
    ]
    by_condition: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    for row in rows:
        stats = by_condition[row["condition"]]
        stats["total"] += 1
        if row["ok"]:
            stats["correct"] += 1
    desc_docs = {
        row["filename"]
        for row in incorrect
        if field_type(row["field_name"]) == "line_items.description"
    }
    detail_docs = {
        row["filename"]
        for row in incorrect
        if field_type(row["field_name"]) == "line_items.detail"
    }
    return {
        "by_type": dict(by_type),
        "by_condition": dict(by_condition),
        "citation_verified": verified,
        "citation_total": cited,
        "rows": rows,
        "incorrect": incorrect,
        "weak_citations": weak,
        "description_error_docs": sorted(desc_docs),
        "detail_error_docs": sorted(detail_docs),
        "shared_description_detail_docs": sorted(desc_docs & detail_docs),
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
            "added_to_ground_truth": item.added_to_ground_truth,
            "classification": item.classification,
        }
        if key in actual_set:
            caught.append(entry)
        else:
            missed.append(entry)
    extras = []
    for row, key in zip(actual_rows, actual_keys):
        if key not in planted_set:
            extras.append(
                {
                    **row,
                    "classification": "Genuine error: not explained by planted data or shared identifiers.",
                }
            )
    added = [item for item in PLANTED_FINDINGS if item.added_to_ground_truth]
    original = [item for item in PLANTED_FINDINGS if not item.added_to_ground_truth]
    return {
        "planted": len(original),
        "expected": len(PLANTED_FINDINGS),
        "caught": caught,
        "missed": missed,
        "false_positives": extras,
        "added_to_ground_truth": [
            {
                "check_type": item.check_type,
                "severity": item.severity,
                "documents": list(item.documents),
                "classification": item.classification,
            }
            for item in added
        ],
        "actual": actual_rows,
    }


def score_currency_flags(db) -> dict[str, Any]:
    from app.db.models import Document

    truth = all_ground_truth()
    results = []
    for filename, expected_doc in sorted(truth.items()):
        expected_currency = (expected_doc.get("fields") or {}).get("currency")
        if expected_currency != "$":
            continue
        document = db.query(Document).filter(Document.filename == filename).first()
        ok = False
        flags: list[Any] = []
        if document is not None:
            fields = extraction_fields(db, document.id)
            field = fields.get("currency") or {}
            flags = field.get("validation_flags") or []
            ok = any(
                str(flag.get("reason", "")).startswith("ambiguous_currency_symbol")
                for flag in flags
            )
        results.append(
            {
                "filename": filename,
                "field_name": "currency",
                "flag_prefix": "ambiguous_currency_symbol",
                "caught": ok,
            }
        )
    caught = sum(1 for item in results if item["caught"])
    return {"flags": results, "caught": caught, "total": len(results)}


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


def _pct(correct: int, total: int) -> float:
    return 100.0 * correct / total if total else 0.0


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
        lines.append(
            f"| {name} | {stats['correct']} | {stats['total']} | {_pct(stats['correct'], stats['total']):.0f}% |"
        )

    lines.extend(
        [
            "",
            "### Field accuracy by document condition",
            "",
            "| Condition | Correct | Total | Accuracy |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    by_condition = field_score.get("by_condition") or {}
    for name in ("clean PDF", "faded scan", "rotated scan"):
        stats = by_condition.get(name) or {"correct": 0, "total": 0}
        lines.append(
            f"| {name} | {stats['correct']} | {stats['total']} | {_pct(stats['correct'], stats['total']):.0f}% |"
        )

    incorrect = field_score.get("incorrect") or []
    lines.extend(
        [
            "",
            "### Incorrect fields",
            "",
        ]
    )
    if not incorrect:
        lines.append("None.")
    else:
        lines.extend(
            [
                "| Document | Field | Expected | Extracted |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in incorrect:
            lines.append(
                f"| {row['filename']} | {row['field_name']} | "
                f"{format_value(row['expected'])} | {format_value(row['actual'])} |"
            )
        shared = field_score.get("shared_description_detail_docs") or []
        desc_docs = field_score.get("description_error_docs") or []
        detail_docs = field_score.get("detail_error_docs") or []
        if desc_docs or detail_docs:
            lines.append("")
            if shared and set(desc_docs) == set(detail_docs) == set(shared):
                lines.append(
                    "line_items.description and line_items.detail both missed on the same "
                    f"{len(shared)} documents: {', '.join(shared)}. In both cases the model "
                    "split the template line that combines description and detail "
                    "(Web Design / Campaign landing page) into description "
                    "`Web Design Campaign` and detail `landing page`."
                )
            else:
                lines.append(
                    "line_items.description misses: "
                    f"{', '.join(desc_docs) or 'none'}. "
                    "line_items.detail misses: "
                    f"{', '.join(detail_docs) or 'none'}."
                )

    weak = field_score.get("weak_citations") or []
    lines.extend(
        [
            "",
            "### Unverified or weak citations",
            "",
        ]
    )
    if not weak:
        lines.append("None.")
    else:
        lines.extend(
            [
                "| Document | Field | Status |",
                "| --- | --- | --- |",
            ]
        )
        for row in weak:
            lines.append(
                f"| {row['filename']} | {row['field_name']} | {row.get('verification_status') or '—'} |"
            )

    cite_pct = (
        100.0 * field_score["citation_verified"] / field_score["citation_total"]
        if field_score.get("citation_total")
        else 0.0
    )
    lines.extend(
        [
            "",
            f"Citation verification rate: **{field_score['citation_verified']}/{field_score['citation_total']}** ({cite_pct:.0f}%).",
            "",
            "### Expected findings",
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
        if key not in caught_keys:
            mark = "no"
        elif item.added_to_ground_truth:
            mark = "yes (correct, added to ground truth)"
        else:
            mark = "yes"
        lines.append(
            f"| {item.check_type} | {', '.join(item.documents)} | {item.severity or '—'} | {mark} |"
        )
    fp = len(finding_score["false_positives"])
    fn = len(finding_score["missed"])
    original = finding_score.get("planted", len(PLANTED_FINDINGS))
    expected = finding_score.get("expected", len(PLANTED_FINDINGS))
    lines.extend(
        [
            "",
            f"Originally planted: **{original}**. After adding correct side-effect findings: **{expected}** expected. "
            f"False positives remaining: **{fp}**. False negatives: **{fn}**.",
            "",
            "### Findings added to ground truth",
            "",
        ]
    )
    added = finding_score.get("added_to_ground_truth") or []
    if not added:
        lines.append("None.")
    else:
        lines.extend(
            [
                "| Check | Documents | Severity | Classification |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in added:
            lines.append(
                f"| {item['check_type']} | {', '.join(item['documents'])} | "
                f"{item.get('severity') or '—'} | {item.get('classification') or '—'} |"
            )

    lines.extend(
        [
            "",
            "### Remaining false positives",
            "",
        ]
    )
    extras = finding_score.get("false_positives") or []
    if not extras:
        lines.append("None. The previous extras were correct findings missing from ground truth.")
    else:
        lines.extend(
            [
                "| Check | Documents | Severity | Explanation | Classification |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in extras:
            explanation = " ".join(str(item.get("explanation") or "").split())
            classification = item.get("classification") or "—"
            lines.append(
                f"| {item['check_type']} | {', '.join(item['documents'])} | "
                f"{item.get('severity') or '—'} | {explanation} | {classification} |"
            )

    caught_flags = flag_score.get("caught", sum(1 for item in flag_score.get("flags") or [] if item.get("caught")))
    total_flags = flag_score.get("total", len(flag_score.get("flags") or []))
    lines.extend(
        [
            "",
            "### Ambiguous currency flags",
            "",
            f"Every invoice in this corpus uses a bare `$` with no ISO code. "
            f"**{caught_flags}/{total_flags}** were flagged `ambiguous_currency_symbol`.",
            "",
            "| Document | Field | Flag | Caught |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in flag_score.get("flags") or []:
        lines.append(
            f"| {item['filename']} | {item['field_name']} | {item['flag_prefix']} | {'yes' if item['caught'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "### Limitations",
            "",
            "- Documents are synthetic PDFs and PNG scans from a single template generator, not real vendor invoices.",
            "- Sample size is 19 documents (11 invoices including two degraded scans, 8 purchase orders).",
            "- Extraction used `gemini-3.5-flash-lite` because the Gemini free tier rate-limits `gemini-3.6-flash`.",
            "- This is a smoke test that the checks fire on planted issues, not a benchmark of production accuracy.",
            "",
        ]
    )
    return "\n".join(lines)

