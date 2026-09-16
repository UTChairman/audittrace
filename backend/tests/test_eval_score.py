from pathlib import Path

from eval.cases import PLANTED_FINDINGS, all_ground_truth, audit_filenames
from eval.generate import generate_all
from eval.score import finding_identity, render_markdown, values_match


def test_ground_truth_covers_planted_documents() -> None:
    truth = all_ground_truth()
    for item in PLANTED_FINDINGS:
        for name in item.documents:
            assert name in truth, name
    assert "inv_clean.pdf" in audit_filenames()
    assert "inv_clean_rotated.png" not in audit_filenames()


def test_values_match_numbers_and_text() -> None:
    assert values_match("total", 93.5, 93.50)
    assert values_match("vendor_name", "Northbridge Studio", "northbridge  studio")
    assert not values_match("vendor_name", "Northbridge Studio", "Globex")


def test_generate_writes_pdfs(tmp_path: Path) -> None:
    written = generate_all(tmp_path)
    names = {path.name for path in written}
    assert "inv_clean.pdf" in names
    assert "po_clean.pdf" in names
    assert "inv_clean_copy.pdf" in names
    assert "inv_clean_rotated.png" in names
    clean = (tmp_path / "inv_clean.pdf").read_bytes()
    copy = (tmp_path / "inv_clean_copy.pdf").read_bytes()
    assert clean == copy
    assert (tmp_path / "inv_clean.pdf").stat().st_size > 1000


def test_render_markdown_includes_accuracy_table() -> None:
    field_score = {
        "by_type": {"total": {"correct": 8, "total": 10}, "vendor_name": {"correct": 9, "total": 10}},
        "citation_verified": 40,
        "citation_total": 50,
        "rows": [],
    }
    finding_score = {
        "planted": len(PLANTED_FINDINGS),
        "caught": [
            {
                "check_type": item.check_type,
                "severity": item.severity,
                "documents": list(item.documents),
            }
            for item in PLANTED_FINDINGS
        ],
        "missed": [],
        "false_positives": [],
        "actual": [],
    }
    markdown = render_markdown(
        field_score,
        finding_score,
        {"flags": [{"filename": "inv_clean.pdf", "field_name": "currency", "flag_prefix": "ambiguous_currency_symbol", "caught": True}]},
    )
    assert "| Field type |" in markdown
    assert "vendor_mismatch" in markdown
    assert "False positives: **0**" in markdown
    assert "yes" in markdown


def test_finding_identity_separates_total_severities() -> None:
    high = finding_identity("total_mismatch", {"a.pdf", "b.pdf"}, "high")
    medium = finding_identity("total_mismatch", {"a.pdf", "b.pdf"}, "medium")
    assert high != medium
