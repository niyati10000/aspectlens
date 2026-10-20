"""Text preprocessing, PII stripping, contraction expansion, and character offset mapping."""

import re

# Regex patterns for PII stripping
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", re.IGNORECASE
)
PHONE_REGEX = re.compile(
    r"\b(?:\+?(\d{1,3}))?[-.\s]?(?:\(?(\d{3})\)?[-.\s]?)?(\d{3})[-.\s]?(\d{4})\b"
)
URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
)
HTML_TAG_REGEX = re.compile(r"<[^>]+>")
WHITESPACE_REGEX = re.compile(r"\s+")


def strip_pii(text: str) -> str:
    """Strip personally identifiable information (emails, phone numbers, URLs, HTML tags) from review text."""
    if not text:
        return ""
    text = HTML_TAG_REGEX.sub(" ", text)
    text = EMAIL_REGEX.sub("[EMAIL]", text)
    text = PHONE_REGEX.sub("[PHONE]", text)
    text = URL_REGEX.sub("[URL]", text)
    text = WHITESPACE_REGEX.sub(" ", text).strip()
    return text


def clean_text(text: str) -> str:
    """Preprocess text: clean whitespace and strip PII while preserving readable structure."""
    return strip_pii(text)
