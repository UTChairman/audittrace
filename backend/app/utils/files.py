from pathlib import Path

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
}

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    return name.replace("..", "_").strip() or "upload"


def detect_image_suffix(content_type: str, filename: str) -> str:
    if content_type == "image/png":
        return "png"
    if content_type == "image/jpeg":
        return "jpg"
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in {"png", "jpg", "jpeg"}:
        return "jpg" if ext == "jpeg" else ext
    raise ValueError(f"Unsupported image type: {content_type}")
