from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_cache_id: Mapped[int | None] = mapped_column(
        ForeignKey("ocr_caches.id"), nullable=True
    )
    duplicate_of_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    ocr_cache: Mapped["OcrCache | None"] = relationship(back_populates="documents")
    classification: Mapped["DocumentClassification | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    extractions: Mapped[list["Extraction"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    findings: Mapped[list["AuditFinding"]] = relationship(
        back_populates="document",
        foreign_keys="AuditFinding.document_id",
        cascade="all, delete-orphan",
    )


class OcrCache(Base):
    __tablename__ = "ocr_caches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    documents: Mapped[list[Document]] = relationship(back_populates="ocr_cache")
    page_results: Mapped[list["OcrPageResult"]] = relationship(
        back_populates="ocr_cache", cascade="all, delete-orphan"
    )
    blocks: Mapped[list["OcrBlock"]] = relationship(
        back_populates="ocr_cache", cascade="all, delete-orphan"
    )
    paragraphs: Mapped[list["OcrParagraph"]] = relationship(
        back_populates="ocr_cache", cascade="all, delete-orphan"
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped[Document] = relationship(back_populates="pages")


class OcrPageResult(Base):
    __tablename__ = "ocr_page_results"
    __table_args__ = (UniqueConstraint("ocr_cache_id", "page_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ocr_cache_id: Mapped[int] = mapped_column(
        ForeignKey("ocr_caches.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_vision_response: Mapped[str] = mapped_column(Text, nullable=False)

    ocr_cache: Mapped[OcrCache] = relationship(back_populates="page_results")


class OcrBlock(Base):
    __tablename__ = "ocr_blocks"
    __table_args__ = (UniqueConstraint("ocr_cache_id", "page_number", "block_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ocr_cache_id: Mapped[int] = mapped_column(
        ForeignKey("ocr_caches.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    ocr_cache: Mapped[OcrCache] = relationship(back_populates="blocks")


class OcrParagraph(Base):
    __tablename__ = "ocr_paragraphs"
    __table_args__ = (
        UniqueConstraint(
            "ocr_cache_id", "page_number", "block_index", "paragraph_index"
        ),
        Index("ix_ocr_paragraphs_lookup", "ocr_cache_id", "page_number", "page_paragraph_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ocr_cache_id: Mapped[int] = mapped_column(
        ForeignKey("ocr_caches.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    ocr_cache: Mapped[OcrCache] = relationship(back_populates="paragraphs")
    words: Mapped[list["OcrWord"]] = relationship(
        back_populates="paragraph", cascade="all, delete-orphan"
    )


class OcrWord(Base):
    __tablename__ = "ocr_words"
    __table_args__ = (UniqueConstraint("paragraph_id", "word_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paragraph_id: Mapped[int] = mapped_column(
        ForeignKey("ocr_paragraphs.id", ondelete="CASCADE"), nullable=False
    )
    word_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    paragraph: Mapped[OcrParagraph] = relationship(back_populates="words")


class DocumentClassification(Base):
    __tablename__ = "document_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    document: Mapped[Document] = relationship(back_populates="classification")


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schema_type: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_llm_response: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    document: Mapped[Document] = relationship(back_populates="extractions")
    fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="extraction", cascade="all, delete-orphan"
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (UniqueConstraint("extraction_id", "field_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[int] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_paragraph_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    supporting_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_flags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    original_ai_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    extraction: Mapped[Extraction] = relationship(back_populates="fields")


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    related_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    field_citations: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    document: Mapped[Document] = relationship(
        back_populates="findings", foreign_keys=[document_id]
    )


settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
