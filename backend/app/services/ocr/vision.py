import base64
import json
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


class VisionOcrError(Exception):
    """Raised when the Vision API returns an error."""


async def annotate_image(image_bytes: bytes) -> dict:
    """Send one image to Google Cloud Vision DOCUMENT_TEXT_DETECTION."""
    settings = get_settings()
    if not settings.google_vision_api_key:
        raise VisionOcrError("GOOGLE_VISION_API_KEY is not configured")

    payload = {
        "requests": [
            {
                "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            VISION_URL,
            params={"key": settings.google_vision_api_key},
            json=payload,
        )

    if response.status_code == 429:
        raise VisionOcrError("Vision API rate limit exceeded")
    if response.status_code >= 400:
        logger.error("Vision API request failed with status %s", response.status_code)
        raise VisionOcrError(
            f"Vision API request failed with status {response.status_code}"
        )

    data = response.json()
    responses = data.get("responses") or []
    if responses and "error" in responses[0]:
        message = responses[0]["error"].get("message", "Unknown Vision API error")
        raise VisionOcrError(message)

    return data


def serialize_vision_response(response: dict) -> str:
    return json.dumps(response)
