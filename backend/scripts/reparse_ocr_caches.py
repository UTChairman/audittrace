"""Reparse stored Vision OCR responses without calling the Vision API."""

from app.db.models import SessionLocal, init_db
from app.services.ocr.repository import reparse_all_ocr_caches


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        cache_count, page_count = reparse_all_ocr_caches(db)
        print(f"Reparsed {cache_count} OCR cache(s), {page_count} page(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
