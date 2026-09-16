import pytest

from app.utils.files import resolve_data_file, to_data_relative_path


def test_to_data_relative_path_from_absolute_windows_path(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    pages_dir = data_dir / "pages" / "1"
    pages_dir.mkdir(parents=True)
    image_path = pages_dir / "page_1.png"
    image_path.write_bytes(b"png")

    monkeypatch.setattr("app.utils.files.DATA_DIR", data_dir)

    relative = to_data_relative_path(str(image_path))
    assert relative == "pages/1/page_1.png"


def test_to_data_relative_path_from_host_windows_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.utils.files.DATA_DIR", tmp_path)
    relative = to_data_relative_path(
        r"C:\Users\omart\Downloads\audittrace\data\pages\1\page_1.png"
    )
    assert relative == "pages/1/page_1.png"


def test_resolve_data_file_remaps_windows_path_onto_current_data_dir(tmp_path, monkeypatch) -> None:
    pages = tmp_path / "pages" / "1"
    pages.mkdir(parents=True)
    image = pages / "page_1.png"
    image.write_bytes(b"png")
    monkeypatch.setattr("app.utils.files.DATA_DIR", tmp_path)
    resolved = resolve_data_file(r"C:\Users\omart\Downloads\audittrace\data\pages\1\page_1.png")
    assert resolved == image.resolve()
