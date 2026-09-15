import hashlib
import re
from dataclasses import dataclass

STABLE_ID_PATTERN = re.compile(
    r"^doc(?P<document_id>\d+)_p(?P<page>\d+)_para(?P<index>\d+)$"
)


@dataclass(frozen=True)
class ParsedStableId:
    document_id: int
    page_number: int
    paragraph_index: int


def build_stable_id(
    document_id: int, page_number: int, paragraph_index: int
) -> str:
    """Build a document-scoped paragraph stable ID, e.g. doc3_p2_para14."""
    if document_id < 1:
        raise ValueError("document_id must be >= 1")
    if page_number < 1:
        raise ValueError("page_number must be >= 1")
    if paragraph_index < 1:
        raise ValueError("paragraph_index must be >= 1")
    return f"doc{document_id}_p{page_number}_para{paragraph_index}"


def parse_stable_id(stable_id: str) -> ParsedStableId:
    """Parse a stable ID back into document_id, page_number, paragraph_index."""
    match = STABLE_ID_PATTERN.match(stable_id)
    if not match:
        raise ValueError(f"Invalid stable ID format: {stable_id!r}")
    document_id = int(match.group("document_id"))
    page_number = int(match.group("page"))
    paragraph_index = int(match.group("index"))
    if document_id < 1 or page_number < 1 or paragraph_index < 1:
        raise ValueError(f"Invalid stable ID values: {stable_id!r}")
    return ParsedStableId(
        document_id=document_id,
        page_number=page_number,
        paragraph_index=paragraph_index,
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
