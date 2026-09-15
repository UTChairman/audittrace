from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Document
from app.services.extraction.pipeline import list_ocr_complete_document_ids


def test_list_ocr_complete_document_ids_skips_other_statuses() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db: Session = sessionmaker(bind=engine)()
    for filename, status in (
        ("old.pdf", "ocr_complete"),
        ("done.pdf", "extracted"),
        ("also-old.pdf", "ocr_complete"),
        ("pending.pdf", "pending"),
    ):
        db.add(
            Document(
                filename=filename,
                content_type="application/pdf",
                file_hash=filename,
                file_size_bytes=1,
                storage_path=filename,
                status=status,
            )
        )
    db.commit()
    assert list_ocr_complete_document_ids(db) == [1, 3]
