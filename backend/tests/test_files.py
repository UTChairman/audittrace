import pytest

from app.utils.files import to_data_relative_path


def test_to_data_relative_path_from_absolute_windows_path(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    pages_dir = data_dir / "pages" / "1"
    pages_dir.mkdir(parents=True)
    image_path = pages_dir / "page_1.png"
    image_path.write_bytes(b"png")

    monkeypatch.setattr("app.utils.files.DATA_DIR", data_dir)

    relative = to_data_relative_path(str(image_path))
    assert relative == "pages/1/page_1.png"
