import json

from sqlalchemy.orm import Session

from app.db.models import OcrBlock, OcrCache, OcrPageResult, OcrParagraph, OcrWord
from app.services.ocr.parser import ParsedPage, parse_vision_page_response


def delete_parsed_ocr_for_cache(db: Session, ocr_cache_id: int) -> None:
    """Remove parsed OCR rows for a cache, keeping raw Vision page results."""
    paragraph_ids = [
        row.id
        for row in db.query(OcrParagraph.id)
        .filter(OcrParagraph.ocr_cache_id == ocr_cache_id)
        .all()
    ]
    if paragraph_ids:
        db.query(OcrWord).filter(OcrWord.paragraph_id.in_(paragraph_ids)).delete(
            synchronize_session=False
        )
    db.query(OcrParagraph).filter(OcrParagraph.ocr_cache_id == ocr_cache_id).delete(
        synchronize_session=False
    )
    db.query(OcrBlock).filter(OcrBlock.ocr_cache_id == ocr_cache_id).delete(
        synchronize_session=False
    )


def save_parsed_page(
    db: Session, ocr_cache_id: int, parsed: ParsedPage, raw_response: dict | None = None
) -> None:
    """Persist parsed OCR hierarchy for one page."""
    if raw_response is not None:
        db.add(
            OcrPageResult(
                ocr_cache_id=ocr_cache_id,
                page_number=parsed.page_number,
                raw_vision_response=json.dumps(raw_response),
            )
        )

    for block in parsed.blocks:
        db.add(
            OcrBlock(
                ocr_cache_id=ocr_cache_id,
                page_number=parsed.page_number,
                block_index=block.block_index,
                text=block.text,
                bbox_x=block.bbox_x,
                bbox_y=block.bbox_y,
                bbox_width=block.bbox_width,
                bbox_height=block.bbox_height,
                confidence=block.confidence,
            )
        )

    for paragraph in parsed.paragraphs:
        paragraph_row = OcrParagraph(
            ocr_cache_id=ocr_cache_id,
            page_number=parsed.page_number,
            block_index=paragraph.block_index,
            paragraph_index=paragraph.paragraph_index,
            page_paragraph_index=paragraph.page_paragraph_index,
            text=paragraph.text,
            bbox_x=paragraph.bbox_x,
            bbox_y=paragraph.bbox_y,
            bbox_width=paragraph.bbox_width,
            bbox_height=paragraph.bbox_height,
            confidence=paragraph.confidence,
        )
        db.add(paragraph_row)
        db.flush()

        for word in paragraph.words:
            db.add(
                OcrWord(
                    paragraph_id=paragraph_row.id,
                    word_index=word.word_index,
                    text=word.text,
                    bbox_x=word.bbox_x,
                    bbox_y=word.bbox_y,
                    bbox_width=word.bbox_width,
                    bbox_height=word.bbox_height,
                    confidence=word.confidence,
                )
            )


def reparse_ocr_cache(db: Session, ocr_cache_id: int) -> int:
    """Reparse stored Vision responses for one OCR cache. Returns pages reparsed."""
    page_results = (
        db.query(OcrPageResult)
        .filter(OcrPageResult.ocr_cache_id == ocr_cache_id)
        .order_by(OcrPageResult.page_number.asc())
        .all()
    )
    if not page_results:
        return 0

    delete_parsed_ocr_for_cache(db, ocr_cache_id)
    db.flush()

    for page_result in page_results:
        raw_response = json.loads(page_result.raw_vision_response)
        parsed = parse_vision_page_response(raw_response, page_result.page_number)
        save_parsed_page(db, ocr_cache_id, parsed)

    return len(page_results)


def reparse_all_ocr_caches(db: Session) -> tuple[int, int]:
    """Reparse every OCR cache. Returns (cache_count, page_count)."""
    cache_ids = [row.id for row in db.query(OcrCache.id).all()]
    total_pages = 0
    for cache_id in cache_ids:
        total_pages += reparse_ocr_cache(db, cache_id)
    db.commit()
    return len(cache_ids), total_pages
