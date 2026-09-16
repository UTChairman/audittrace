import logging

import pytest

from app.logging_config import (
    RedactGoogleApiKeyFilter,
    configure_logging,
    redact_google_api_keys,
)
from app.services.ocr.vision import VISION_URL, annotate_image


FAKE_KEY = "AIza" + ("B" * 35)


def test_redact_google_api_keys_replaces_exact_key_shape() -> None:
    text = f"POST {VISION_URL}?key={FAKE_KEY} HTTP/1.1"
    assert FAKE_KEY in text
    redacted = redact_google_api_keys(text)
    assert isinstance(redacted, str)
    assert FAKE_KEY not in redacted
    assert "AIza" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_filter_scrubs_log_record_args() -> None:
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: POST %s?key=%s",
        args=(VISION_URL, FAKE_KEY),
        exc_info=None,
    )
    assert RedactGoogleApiKeyFilter().filter(record) is True
    message = record.getMessage()
    assert FAKE_KEY not in message
    assert "AIza" not in message
    assert "[REDACTED]" in message


def test_configure_logging_sets_httpx_and_httpcore_to_warning() -> None:
    configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


@pytest.mark.asyncio
async def test_annotate_image_sends_api_key_header(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"responses": [{}]}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, headers=None, json=None, params=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.services.ocr.vision.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(
        "app.services.ocr.vision.get_settings",
        lambda: type("S", (), {"google_vision_api_key": FAKE_KEY})(),
    )
    await annotate_image(b"image-bytes")
    assert captured["url"] == VISION_URL
    assert captured["params"] is None
    assert captured["headers"]["X-Goog-Api-Key"] == FAKE_KEY
    assert "key" not in (captured["url"] or "")
