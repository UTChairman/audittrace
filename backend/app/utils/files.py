from pathlib import Path

from app.config import DATA_DIR

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


def to_data_relative_path(path: str | Path) -> str:
    """Return a path relative to the data directory using forward slashes."""
    path_obj = Path(path)
    absolute = path_obj.resolve()
    data_root = DATA_DIR.resolve()
    try:
        return absolute.relative_to(data_root).as_posix()
    except ValueError:
        parts = path_obj.as_posix().split("/")
        if "data" in parts:
            data_index = parts.index("data")
            return "/".join(parts[data_index + 1 :])
        return path_obj.as_posix()

