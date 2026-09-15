import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PAGES_DIR = DATA_DIR / "pages"


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    google_vision_api_key: str
    gemini_model: str
    max_upload_size_mb: int
    max_pdf_pages: int
    citation_match_threshold: int
    amount_tolerance: float
    database_url: str

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    db_path = DATA_DIR / "audittrace.db"
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        google_vision_api_key=os.getenv("GOOGLE_VISION_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "20")),
        max_pdf_pages=int(os.getenv("MAX_PDF_PAGES", "30")),
        citation_match_threshold=int(os.getenv("CITATION_MATCH_THRESHOLD", "85")),
        amount_tolerance=float(os.getenv("AMOUNT_TOLERANCE", "0.01")),
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}"),
    )


def ensure_data_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
