"""Logging setup that never prints Google API keys or httpx request URLs."""

from __future__ import annotations

import logging
import re

GOOGLE_API_KEY_RE = re.compile(r"AIza[A-Za-z0-9_-]{35}")


def redact_google_api_keys(value: object) -> object:
    if value is None:
        return value
    if isinstance(value, str):
        return GOOGLE_API_KEY_RE.sub("[REDACTED]", value)
    text = str(value)
    redacted = GOOGLE_API_KEY_RE.sub("[REDACTED]", text)
    if redacted != text:
        return redacted
    return value


class RedactGoogleApiKeyFilter(logging.Filter):
    """Strip Google API keys (AIza + 35 characters) from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_google_api_keys(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: redact_google_api_keys(item) for key, item in record.args.items()
                }
            else:
                record.args = tuple(redact_google_api_keys(item) for item in record.args)
        if isinstance(record.exc_text, str):
            record.exc_text = redact_google_api_keys(record.exc_text)
        return True


class RedactGoogleApiKeyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return str(redact_google_api_keys(super().format(record)))


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    redactor = RedactGoogleApiKeyFilter()
    formatter = RedactGoogleApiKeyFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    root = logging.getLogger()
    root.addFilter(redactor)
    for handler in root.handlers:
        handler.addFilter(redactor)
        handler.setFormatter(formatter)
