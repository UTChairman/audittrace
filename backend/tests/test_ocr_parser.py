import pytest

from app.services.ocr.parser import parse_vision_page_response


def _symbol(text: str, break_type: str | None = None) -> dict:
    symbol: dict = {"text": text}
    if break_type is not None:
        symbol["property"] = {"detectedBreak": {"type": break_type}}
    return symbol


def _word(
    text: str,
    trailing_break: str | None = None,
    x: int = 100,
    y: int = 200,
) -> dict:
    symbols = []
    for index, character in enumerate(text):
        break_type = trailing_break if index == len(text) - 1 else None
        symbols.append(_symbol(character, break_type))
    return {
        "boundingBox": {
            "vertices": [
                {"x": x, "y": y},
                {"x": x + 100, "y": y},
                {"x": x + 100, "y": y + 100},
                {"x": x, "y": y + 100},
            ]
        },
        "symbols": symbols,
    }


def _paragraph(words: list[dict]) -> dict:
    return {
        "boundingBox": {
            "vertices": [
                {"x": 100, "y": 200},
                {"x": 500, "y": 200},
                {"x": 500, "y": 400},
                {"x": 100, "y": 400},
            ]
        },
        "words": words,
    }


def _response(*paragraphs: dict) -> dict:
    return {
        "responses": [
            {
                "fullTextAnnotation": {
                    "pages": [
                        {
                            "width": 1000,
                            "height": 2000,
                            "blocks": [
                                {
                                    "boundingBox": {
                                        "vertices": [
                                            {"x": 100, "y": 200},
                                            {"x": 500, "y": 200},
                                            {"x": 500, "y": 400},
                                            {"x": 100, "y": 400},
                                        ]
                                    },
                                    "paragraphs": list(paragraphs),
                                }
                            ],
                        }
                    ]
                }
            }
        ]
    }


@pytest.fixture
def sample_vision_response() -> dict:
    return _response(
        _paragraph(
            [
                _word("Hi"),
            ]
        )
    )


def test_parse_vision_page_response_extracts_hierarchy(
    sample_vision_response: dict,
) -> None:
    parsed = parse_vision_page_response(sample_vision_response, page_number=1)

    assert parsed.page_number == 1
    assert parsed.width_px == 1000
    assert parsed.height_px == 2000
    assert len(parsed.blocks) == 1
    assert len(parsed.paragraphs) == 1
    assert parsed.paragraphs[0].text == "Hi"
    assert parsed.paragraphs[0].page_paragraph_index == 1
    assert parsed.paragraphs[0].bbox_x == pytest.approx(0.1)
    assert parsed.paragraphs[0].bbox_y == pytest.approx(0.1)
    assert parsed.paragraphs[0].bbox_width == pytest.approx(0.4)
    assert parsed.paragraphs[0].bbox_height == pytest.approx(0.1)
    assert len(parsed.paragraphs[0].words) == 1
    assert parsed.paragraphs[0].words[0].text == "Hi"


def test_parse_vision_page_response_rebuilds_text_with_detected_breaks() -> None:
    response = _response(
        _paragraph(
            [
                _word("Invoice", trailing_break="SPACE"),
                _word("Number", trailing_break="EOL_SURE_SPACE"),
            ]
        ),
        _paragraph(
            [
                _word("January", trailing_break="SURE_SPACE", y=300),
                _word("25,", trailing_break="SPACE", x=250, y=300),
                _word("2016", x=350, y=300),
            ]
        ),
    )

    parsed = parse_vision_page_response(response, page_number=1)

    assert parsed.paragraphs[0].text == "Invoice Number"
    assert parsed.paragraphs[0].words[0].text == "Invoice"
    assert parsed.paragraphs[0].words[1].text == "Number"
    assert parsed.blocks[0].text == "Invoice Number\nJanuary 25, 2016"
    assert parsed.paragraphs[1].text == "January 25, 2016"


def test_parse_vision_page_response_handles_hyphen_break_within_word() -> None:
    response = _response(
        _paragraph(
            [
                {
                    "boundingBox": {
                        "vertices": [
                            {"x": 100, "y": 200},
                            {"x": 300, "y": 200},
                            {"x": 300, "y": 300},
                            {"x": 100, "y": 300},
                        ]
                    },
                    "symbols": [
                        _symbol("docu", "HYPHEN"),
                        _symbol("ment"),
                    ],
                }
            ]
        )
    )

    parsed = parse_vision_page_response(response, page_number=1)

    assert parsed.paragraphs[0].words[0].text == "docu-ment"
    assert parsed.paragraphs[0].text == "docu-ment"


def test_parse_vision_page_response_handles_empty_annotation() -> None:
    parsed = parse_vision_page_response({"responses": [{}]}, page_number=2)
    assert parsed.page_number == 2
    assert parsed.blocks == []
    assert parsed.paragraphs == []


def test_parse_vision_page_response_raises_on_api_error() -> None:
    with pytest.raises(ValueError, match="Vision API error"):
        parse_vision_page_response(
            {"responses": [{"error": {"message": "Bad request"}}]},
            page_number=1,
        )
