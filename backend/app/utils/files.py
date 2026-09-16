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
    raw = str(path).replace("\\", "/")
    path_obj = Path(raw)
    try:
        absolute = path_obj.resolve()
        data_root = DATA_DIR.resolve()
        return absolute.relative_to(data_root).as_posix()
    except (ValueError, OSError):
        pass
    parts = [part for part in raw.split("/") if part]
    if "data" in parts:
        data_index = parts.index("data")
        return "/".join(parts[data_index + 1 :])
    return path_obj.as_posix().lstrip("/")


def resolve_data_file(stored: str) -> Path | None:
    """Map a stored relative or host-absolute data path onto the current DATA_DIR."""
    relative = to_data_relative_path(stored)
    candidate = Path(relative)
    if candidate.is_absolute():
        path = candidate.resolve()
    else:
        path = (DATA_DIR / relative).resolve()
    data_root = DATA_DIR.resolve()
    if path != data_root and data_root not in path.parents:
        return None
    return path

