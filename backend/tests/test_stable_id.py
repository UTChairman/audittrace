import pytest

from app.utils.hashing import build_stable_id, parse_stable_id


def test_build_stable_id() -> None:
    assert build_stable_id(3, 2, 14) == "doc3_p2_para14"


def test_parse_stable_id() -> None:
    parsed = parse_stable_id("doc3_p2_para14")
    assert parsed.document_id == 3
    assert parsed.page_number == 2
    assert parsed.paragraph_index == 14


def test_build_and_parse_round_trip() -> None:
    stable_id = build_stable_id(12, 1, 5)
    parsed = parse_stable_id(stable_id)
    assert parsed.document_id == 12
    assert parsed.page_number == 1
    assert parsed.paragraph_index == 5


@pytest.mark.parametrize(
    "invalid_id",
    ["doc3_p2", "3_p2_para14", "doc3_p2_para", "doc0_p1_para1"],
)
def test_parse_stable_id_rejects_invalid_values(invalid_id: str) -> None:
    with pytest.raises(ValueError):
        parse_stable_id(invalid_id)


def test_build_stable_id_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        build_stable_id(0, 1, 1)
    with pytest.raises(ValueError):
        build_stable_id(1, 0, 1)
    with pytest.raises(ValueError):
        build_stable_id(1, 1, 0)
