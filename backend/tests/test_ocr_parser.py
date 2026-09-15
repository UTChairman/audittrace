import pytest

from app.services.ocr.parser import parse_vision_page_response


@pytest.fixture
def sample_vision_response() -> dict:
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
                                            {"x": 400, "y": 200},
                                            {"x": 400, "y": 300},
                                            {"x": 100, "y": 300},
                                        ]
                                    },
                                    "paragraphs": [
                                        {
                                            "boundingBox": {
                                                "vertices": [
                                                    {"x": 100, "y": 200},
                                                    {"x": 400, "y": 200},
                                                    {"x": 400, "y": 300},
                                                    {"x": 100, "y": 300},
                                                ]
                                            },
                                            "words": [
                                                {
                                                    "boundingBox": {
                                                        "vertices": [
                                                            {"x": 100, "y": 200},
                                                            {"x": 200, "y": 200},
                                                            {"x": 200, "y": 300},
                                                            {"x": 100, "y": 300},
                                                        ]
                                                    },
                                                    "symbols": [
                                                        {"text": "H", "confidence": 0.9},
                                                        {"text": "i", "confidence": 0.8},
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
        ]
    }


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
    assert parsed.paragraphs[0].bbox_width == pytest.approx(0.3)
    assert parsed.paragraphs[0].bbox_height == pytest.approx(0.05)
    assert parsed.paragraphs[0].confidence == pytest.approx(0.85)
    assert len(parsed.paragraphs[0].words) == 1
    assert parsed.paragraphs[0].words[0].text == "Hi"


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
