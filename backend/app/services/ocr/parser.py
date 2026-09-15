from dataclasses import dataclass, field
from statistics import mean


@dataclass
class ParsedWord:
    word_index: int
    text: str
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    confidence: float | None


@dataclass
class ParsedParagraph:
    block_index: int
    paragraph_index: int
    page_paragraph_index: int
    text: str
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    confidence: float | None
    words: list[ParsedWord] = field(default_factory=list)


@dataclass
class ParsedBlock:
    block_index: int
    text: str
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    confidence: float | None
    paragraphs: list[ParsedParagraph] = field(default_factory=list)


@dataclass
class ParsedPage:
    page_number: int
    width_px: int
    height_px: int
    blocks: list[ParsedBlock] = field(default_factory=list)
    paragraphs: list[ParsedParagraph] = field(default_factory=list)


def _vertices_to_bbox(
    vertices: list[dict[str, float | int]], page_width: int, page_height: int
) -> tuple[float, float, float, float]:
    if page_width <= 0 or page_height <= 0:
        raise ValueError("Page dimensions must be positive")
    xs = [float(v.get("x", 0)) for v in vertices]
    ys = [float(v.get("y", 0)) for v in vertices]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return (
        x_min / page_width,
        y_min / page_height,
        max(x_max - x_min, 0.0) / page_width,
        max(y_max - y_min, 0.0) / page_height,
    )


def _average_confidence(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return float(mean(present))


def _word_text_and_confidence(word: dict) -> tuple[str, float | None]:
    symbols = word.get("symbols") or []
    text = "".join(symbol.get("text", "") for symbol in symbols)
    confidences = [symbol.get("confidence") for symbol in symbols if "confidence" in symbol]
    confidence = float(mean(confidences)) if confidences else word.get("confidence")
    if confidence is not None:
        confidence = float(confidence)
    return text, confidence


def parse_vision_page_response(
    vision_response: dict, page_number: int
) -> ParsedPage:
    """Parse a Vision API annotate response for one page."""
    responses = vision_response.get("responses") or []
    if not responses:
        raise ValueError("Vision response missing 'responses'")

    first = responses[0]
    if "error" in first:
        message = first["error"].get("message", "Unknown Vision API error")
        raise ValueError(f"Vision API error: {message}")

    annotation = first.get("fullTextAnnotation")
    if not annotation:
        pages = []
    else:
        pages = annotation.get("pages") or []

    if not pages:
        return ParsedPage(page_number=page_number, width_px=1, height_px=1)

    page = pages[0]
    page_width = int(page.get("width") or 1)
    page_height = int(page.get("height") or 1)
    parsed = ParsedPage(
        page_number=page_number,
        width_px=page_width,
        height_px=page_height,
    )

    page_paragraph_counter = 0
    for block_index, block in enumerate(page.get("blocks") or []):
        block_vertices = (block.get("boundingBox") or {}).get("vertices") or []
        block_bbox = _vertices_to_bbox(block_vertices, page_width, page_height)
        parsed_block = ParsedBlock(
            block_index=block_index,
            text="",
            bbox_x=block_bbox[0],
            bbox_y=block_bbox[1],
            bbox_width=block_bbox[2],
            bbox_height=block_bbox[3],
            confidence=None,
        )

        block_paragraphs: list[ParsedParagraph] = []
        for paragraph_index, paragraph in enumerate(block.get("paragraphs") or []):
            page_paragraph_counter += 1
            paragraph_vertices = (paragraph.get("boundingBox") or {}).get("vertices") or []
            para_bbox = _vertices_to_bbox(paragraph_vertices, page_width, page_height)

            parsed_words: list[ParsedWord] = []
            word_texts: list[str] = []
            word_confidences: list[float | None] = []

            for word_index, word in enumerate(paragraph.get("words") or []):
                word_vertices = (word.get("boundingBox") or {}).get("vertices") or []
                word_bbox = _vertices_to_bbox(word_vertices, page_width, page_height)
                word_text, word_confidence = _word_text_and_confidence(word)
                word_texts.append(word_text)
                word_confidences.append(word_confidence)
                parsed_words.append(
                    ParsedWord(
                        word_index=word_index,
                        text=word_text,
                        bbox_x=word_bbox[0],
                        bbox_y=word_bbox[1],
                        bbox_width=word_bbox[2],
                        bbox_height=word_bbox[3],
                        confidence=word_confidence,
                    )
                )

            paragraph_text = "".join(word_texts).strip()
            parsed_paragraph = ParsedParagraph(
                block_index=block_index,
                paragraph_index=paragraph_index,
                page_paragraph_index=page_paragraph_counter,
                text=paragraph_text,
                bbox_x=para_bbox[0],
                bbox_y=para_bbox[1],
                bbox_width=para_bbox[2],
                bbox_height=para_bbox[3],
                confidence=_average_confidence(word_confidences),
                words=parsed_words,
            )
            block_paragraphs.append(parsed_paragraph)
            parsed.paragraphs.append(parsed_paragraph)

        parsed_block.text = "\n".join(p.text for p in block_paragraphs if p.text)
        parsed_block.confidence = _average_confidence(
            [p.confidence for p in block_paragraphs]
        )
        parsed_block.paragraphs = block_paragraphs
        parsed.blocks.append(parsed_block)

    return parsed
