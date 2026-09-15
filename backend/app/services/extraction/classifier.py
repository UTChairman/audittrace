from app.llm.base import LLMProvider, StructuredLLMResult
from app.prompts.loader import load_prompt
from app.schemas.extraction import DocumentClassificationResult
from app.services.ocr.repository import ParagraphWithId


def format_paragraphs_for_prompt(paragraphs: list[ParagraphWithId]) -> str:
    blocks: list[str] = []
    for paragraph in paragraphs:
        confidence = (
            f"{paragraph.confidence:.2f}" if paragraph.confidence is not None else "n/a"
        )
        blocks.append(
            f"{paragraph.stable_id} | page={paragraph.page_number} | conf={confidence}\n"
            f"{paragraph.text}"
        )
    return "\n\n".join(blocks)


async def classify_document(
    provider: LLMProvider,
    paragraphs: list[ParagraphWithId],
) -> StructuredLLMResult[DocumentClassificationResult]:
    prompt = load_prompt("classify_document.txt") + "\n\n" + format_paragraphs_for_prompt(paragraphs)
    return await provider.generate_structured(
        prompt=prompt,
        response_schema=DocumentClassificationResult,
    )
