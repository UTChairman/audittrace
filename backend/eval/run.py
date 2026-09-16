"""Run OCR, extraction, and audit on synthetic documents using a separate database."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from eval.cases import all_ground_truth
from eval.generate import generate_all
from eval.runtime import EVAL_DOCS, EVAL_RESULTS, EVAL_ROOT, bootstrap_eval
from eval.score import render_markdown, score_currency_flags, score_fields, score_findings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("eval.run")

TERMINAL_OK = {"extracted"}


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "application/octet-stream"


def register_document(db, path: Path):
    from app.config import UPLOADS_DIR
    from app.db.models import Document, OcrCache
    from app.utils.hashing import sha256_hex

    existing = db.query(Document).filter(Document.filename == path.name).first()
    if existing is not None:
        return existing
    content = path.read_bytes()
    file_hash = sha256_hex(content)
    first = (
        db.query(Document)
        .filter(Document.file_hash == file_hash)
        .order_by(Document.id.asc())
        .first()
    )
    cache = db.query(OcrCache).filter(OcrCache.file_hash == file_hash).first()
    document = Document(
        filename=path.name,
        content_type=_content_type(path),
        file_hash=file_hash,
        file_size_bytes=len(content),
        storage_path="",
        status="pending",
        duplicate_of_document_id=first.id if first else None,
        ocr_cache_id=cache.id if cache else None,
    )
    db.add(document)
    db.flush()
    stored = UPLOADS_DIR / f"{document.id}_{path.name}"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(content)
    document.storage_path = str(stored)
    db.commit()
    db.refresh(document)
    return document


async def process_one(document_id: int) -> None:
    from app.services.ingestion import process_uploaded_document

    await process_uploaded_document(document_id)


async def run_corpus(*, delay_seconds: float, report_only: bool) -> None:
    from app.db.models import Document, get_session
    from app.services.audit.pipeline import run_audit

    bootstrap_eval()
    generate_all(EVAL_DOCS)
    truth_path = EVAL_ROOT / "ground_truth.json"
    truth_path.write_text(json.dumps(all_ground_truth(), indent=2), encoding="utf-8")

    db = get_session()
    try:
        paths = sorted(EVAL_DOCS.iterdir(), key=lambda item: item.name)
        documents = [register_document(db, path) for path in paths if path.is_file()]
        if not report_only:
            pending = [
                document
                for document in documents
                if document.status not in TERMINAL_OK
            ]
            for index, document in enumerate(pending):
                if index > 0 and delay_seconds > 0:
                    logger.info(
                        "Waiting %.1fs before document %s (%s/%s)",
                        delay_seconds,
                        document.filename,
                        index + 1,
                        len(pending),
                    )
                    await asyncio.sleep(delay_seconds)
                logger.info("Evaluating %s (id=%s, status=%s)", document.filename, document.id, document.status)
                await process_one(document.id)
                db.expire_all()
        run_audit(db)
        field_score = score_fields(db)
        finding_score = score_findings(db)
        flag_score = score_currency_flags(db)
        markdown = render_markdown(field_score, finding_score, flag_score)
        EVAL_RESULTS.write_text(markdown, encoding="utf-8")
        snapshot = {
            "field_score": {
                "by_type": field_score["by_type"],
                "citation_verified": field_score["citation_verified"],
                "citation_total": field_score["citation_total"],
            },
            "finding_score": {
                "planted": finding_score["planted"],
                "caught": finding_score["caught"],
                "missed": finding_score["missed"],
                "false_positives": finding_score["false_positives"],
            },
            "flag_score": flag_score,
        }
        (EVAL_ROOT / "results.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(markdown)
        print(f"Wrote {EVAL_RESULTS}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AuditTrace evaluation on synthetic documents.")
    parser.add_argument(
        "--delay",
        type=float,
        default=20.0,
        help="Seconds to wait between documents (Gemini free-tier friendly). Default: 20",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip OCR/Gemini and score whatever is already in data/eval/eval.db",
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Write PDFs and ground truth, then exit",
    )
    args = parser.parse_args()
    bootstrap_eval()
    if args.generate_only:
        generate_all(EVAL_DOCS)
        (EVAL_ROOT / "ground_truth.json").write_text(
            json.dumps(all_ground_truth(), indent=2), encoding="utf-8"
        )
        print(f"Wrote documents to {EVAL_DOCS}")
        return
    asyncio.run(run_corpus(delay_seconds=args.delay, report_only=args.report_only))


if __name__ == "__main__":
    main()
