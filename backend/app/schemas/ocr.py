from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)


class OcrWordOut(BaseModel):
    word_index: int
    text: str
    bbox: BoundingBox
    confidence: float | None = None


class OcrParagraphOut(BaseModel):
    stable_id: str
    page_number: int
    block_index: int
    paragraph_index: int
    page_paragraph_index: int
    text: str
    bbox: BoundingBox
    confidence: float | None = None
    words: list[OcrWordOut]


class OcrBlockOut(BaseModel):
    page_number: int
    block_index: int
    text: str
    bbox: BoundingBox
    confidence: float | None = None


class OcrPageOut(BaseModel):
    page_number: int
    width_px: int
    height_px: int
    blocks: list[OcrBlockOut]
    paragraphs: list[OcrParagraphOut]


class DocumentOcrOut(BaseModel):
    document_id: int
    status: str
    pages: list[OcrPageOut]


class DocumentPageOut(BaseModel):
    page_number: int
    image_path: str
    width_px: int
    height_px: int


class DocumentOut(BaseModel):
    id: int
    filename: str
    content_type: str
    file_hash: str
    file_size_bytes: int
    status: str
    page_count: int
    ocr_cache_id: int | None
    duplicate_of_document_id: int | None
    error_message: str | None
    pages: list[DocumentPageOut]


class UploadDocumentResult(BaseModel):
    id: int
    filename: str
    status: str
    duplicate_of_document_id: int | None


class UploadResponse(BaseModel):
    documents: list[UploadDocumentResult]
