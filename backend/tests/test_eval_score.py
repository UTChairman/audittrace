from pathlib import Path

from eval.cases import PLANTED_FINDINGS, all_ground_truth, audit_filenames
from eval.generate import generate_all
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Document, DocumentClassification, Extraction
from eval.run import reset_documents_extracted_with_other_models
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


def test_render_markdown_includes_model_column() -> None:
    markdown = render_markdown(
        {
            "by_type": {"total": {"correct": 1, "total": 1}},
            "citation_verified": 1,
            "citation_total": 1,
            "rows": [],
        },
        {
            "planted": len(PLANTED_FINDINGS),
            "caught": [],
            "missed": [],
            "false_positives": [],
            "actual": [],
        },
        {"flags": []},
        {
            "requested": "gemini-3.6-flash",
            "rows": [
                {"filename": "inv_clean.pdf", "status": "extracted", "model": "gemini-3.6-flash"},
                {"filename": "inv_failed.pdf", "status": "extraction_failed", "model": None},
            ],
        },
    )
    assert "Pinned model: **gemini-3.6-flash**" in markdown
    assert "| Document | Status | Model |" in markdown
    assert "| inv_clean.pdf | extracted | gemini-3.6-flash |" in markdown
    assert "| inv_failed.pdf | extraction_failed | — |" in markdown


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


def test_reset_documents_extracted_with_other_models() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    def add_document(filename: str, status: str, model: str) -> Document:
        document = Document(
            filename=filename,
            content_type="application/pdf",
            file_hash=filename,
            file_size_bytes=1,
            storage_path=filename,
            status=status,
        )
        db.add(document)
        db.flush()
        db.add(
            DocumentClassification(
                document_id=document.id,
                document_type="invoice",
                model=model,
            )
        )
        db.add(
            Extraction(
                document_id=document.id,
                schema_type="invoice",
                raw_llm_response="{}",
                model=model,
            )
        )
        return document

    matching = add_document("inv_clean.pdf", "extracted", "gemini-3.6-flash")
    mixed = add_document("inv_lite.pdf", "extracted", "gemini-3.5-flash-lite")
    db.commit()

    reset = reset_documents_extracted_with_other_models(db, "gemini-3.6-flash")
    db.refresh(matching)
    db.refresh(mixed)
    assert reset == 1
    assert matching.status == "extracted"
    assert mixed.status == "ocr_complete"
