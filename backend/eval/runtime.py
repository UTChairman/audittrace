"""Point this process at the evaluation SQLite file and data directory."""

from __future__ import annotations

from pathlib import Path

from app.config import PROJECT_ROOT, ensure_data_dirs
from app.db.models import configure_engine, init_db


EVAL_ROOT = PROJECT_ROOT / "data" / "eval"
EVAL_DB = EVAL_ROOT / "eval.db"
EVAL_DOCS = EVAL_ROOT / "docs"
EVAL_RESULTS = EVAL_ROOT / "results.md"


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def bootstrap_eval() -> Path:
    """Use repository-root data/eval/ (eval.db, docs, results.md), not backend/data."""
    EVAL_ROOT.mkdir(parents=True, exist_ok=True)
    (EVAL_ROOT / "uploads").mkdir(parents=True, exist_ok=True)
    (EVAL_ROOT / "pages").mkdir(parents=True, exist_ok=True)
    EVAL_DOCS.mkdir(parents=True, exist_ok=True)

    import app.config as config

    config.DATA_DIR = EVAL_ROOT
    config.UPLOADS_DIR = EVAL_ROOT / "uploads"
    config.PAGES_DIR = EVAL_ROOT / "pages"

    import app.services.pdf as pdf_service
    import app.services.review as review_service
    import app.services.upload as upload_service
    import app.utils.files as files_util

    pdf_service.PAGES_DIR = config.PAGES_DIR
    upload_service.UPLOADS_DIR = config.UPLOADS_DIR
    review_service.DATA_DIR = config.DATA_DIR
    files_util.DATA_DIR = config.DATA_DIR

    configure_engine(f"sqlite:///{EVAL_DB.as_posix()}")
    init_db()
    ensure_data_dirs()
    return EVAL_ROOT
