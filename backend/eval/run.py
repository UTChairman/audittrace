"""Run OCR, extraction, and audit on synthetic documents using a separate database."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from eval.cases import all_ground_truth
from eval.generate import generate_all
from eval.runtime import EVAL_DOCS, EVAL_RESULTS, EVAL_ROOT, EVAL_DB, bootstrap_eval, repo_relative
from eval.score import (
    render_markdown,
    score_currency_flags,
    score_document_models,
    score_fields,
    score_findings,
)
from app.logging_config import configure_logging

configure_logging()
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


def models_used_for_document(db, document_id: int) -> set[str]:
    from app.db.models import DocumentClassification, Extraction

    models: set[str] = set()
    classification = (
        db.query(DocumentClassification)
        .filter(DocumentClassification.document_id == document_id)
        .first()
    )
    if classification is not None and classification.model:
        models.add(classification.model)
    for extraction in db.query(Extraction).filter(Extraction.document_id == document_id):
        if extraction.model:
            models.add(extraction.model)
    return models


def reset_documents_extracted_with_other_models(db, requested_model: str) -> int:
    """Send mixed-model extractions back to ocr_complete so they are re-extracted."""
    from app.db.models import Document

    reset = 0
    for document in db.query(Document).all():
        if document.status not in {"extracted", "extracting"}:
            continue
        models = models_used_for_document(db, document.id)
        if not models or models == {requested_model}:
            continue
        document.status = "ocr_complete"
        document.error_message = None
        reset += 1
        logger.info(
            "Reset %s (id=%s) from models %s to re-extract with %s",
            document.filename,
            document.id,
            ", ".join(sorted(models)),
            requested_model,
        )
    if reset:
        db.commit()
    return reset


def _mark_eval_failed(document_id: int, message: str) -> None:
    from app.db.models import Document, get_session

    db = get_session()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        if document.status in TERMINAL_OK:
            return
        if document.status not in {"failed", "extraction_failed"}:
            document.status = "extraction_failed"
            document.error_message = message
            db.commit()
    finally:
        db.close()


async def process_one(document_id: int, provider) -> None:
    from app.services.ingestion import process_uploaded_document

    await process_uploaded_document(document_id, provider=provider)


async def run_corpus(*, delay_seconds: float, report_only: bool, model: str) -> None:
    from app.db.models import Document, get_session
    from app.llm.gemini import GeminiProvider
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
            reset = reset_documents_extracted_with_other_models(db, model)
            if reset:
                logger.info(
                    "Reset %s document(s) extracted with a different model than %s",
                    reset,
                    model,
                )
            db.expire_all()
            documents = [db.get(Document, document.id) for document in documents]
            provider = GeminiProvider(model=model, fallback_model="")
            logger.info("Evaluating with pinned model %s (fallback disabled)", model)
            pending = [
                document
                for document in documents
                if document is not None and document.status not in TERMINAL_OK
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
                logger.info(
                    "Evaluating %s (id=%s, status=%s, model=%s)",
                    document.filename,
                    document.id,
                    document.status,
                    model,
                )
                try:
                    await process_one(document.id, provider)
                except Exception as exc:
                    logger.exception(
                        "Document %s failed after retries; continuing without switching models",
                        document.filename,
                    )
                    _mark_eval_failed(
                        document.id,
                        f"Evaluation failed after retries: {exc}",
                    )
                db.expire_all()
        run_audit(db)
        field_score = score_fields(db)
        finding_score = score_findings(db)
        flag_score = score_currency_flags(db)
        model_score = score_document_models(db, requested_model=model)
        markdown = render_markdown(field_score, finding_score, flag_score, model_score)
        EVAL_RESULTS.write_text(markdown, encoding="utf-8")
        snapshot = {
            "requested_model": model,
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
            "models": model_score,
        }
        (EVAL_ROOT / "results.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(markdown)
        print(
            f"Wrote {EVAL_RESULTS} (repository-root {repo_relative(EVAL_RESULTS)})"
        )
        print(
            f"Eval database {EVAL_DB} (repository-root {repo_relative(EVAL_DB)})"
        )
    finally:
        db.close()


def main() -> None:
    from app.config import get_settings

    parser = argparse.ArgumentParser(description="Run AuditTrace evaluation on synthetic documents.")
    parser.add_argument(
        "--delay",
        type=float,
        default=20.0,
        help="Seconds to wait between documents (Gemini free-tier friendly). Default: 20",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Gemini model for the whole run with no fallback. Default: GEMINI_MODEL",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip OCR/Gemini and score whatever is already in repository-root data/eval/eval.db",
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
        print(f"Wrote documents to {EVAL_DOCS} (repository-root {repo_relative(EVAL_DOCS)})")
        return
    model = (args.model or get_settings().gemini_model).strip()
    asyncio.run(
        run_corpus(delay_seconds=args.delay, report_only=args.report_only, model=model)
    )


if __name__ == "__main__":
    main()
