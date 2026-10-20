"""Text preprocessing, PII stripping, contraction expansion, and character offset mapping."""

import re
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import spacy

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
WHITESPACE_REGEX = re.compile(r"[ \t\r\f\v]+")
MULTIPLE_NEWLINES_REGEX = re.compile(r"\n\s*\n+")

# Standard English contractions mapping
CONTRACTIONS_MAP = {
    "can't": "cannot",
    "won't": "will not",
    "n't": " not",
    "'re": " are",
    "'s": " is",
    "'d": " would",
    "'ll": " will",
    "'t": " not",
    "'ve": " have",
    "'m": " am",
}


def strip_pii(text: str) -> str:
    """Strip personally identifiable information (emails, phone numbers, URLs, HTML tags) from review text."""
    if not text:
        return ""
    text = HTML_TAG_REGEX.sub(" ", text)
    text = EMAIL_REGEX.sub("[EMAIL]", text)
    text = PHONE_REGEX.sub("[PHONE]", text)
    text = URL_REGEX.sub("[URL]", text)
    return text


def clean_whitespace(text: str) -> str:
    """Normalize internal spaces and newlines without collapsing punctuation."""
    if not text:
        return ""
    text = MULTIPLE_NEWLINES_REGEX.sub("\n", text)
    text = WHITESPACE_REGEX.sub(" ", text)
    return text.strip()


def clean_text(text: str) -> str:
    """Preprocess text: clean HTML, strip PII, and normalize whitespace."""
    if not text:
        return ""
    return clean_whitespace(strip_pii(text))


def expand_contractions(text: str) -> str:
    """Expand common English contractions for normalized text matching."""
    if not text:
        return ""
    # Process word-level contractions case-insensitively
    pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in CONTRACTIONS_MAP.keys()) + r")\b", re.IGNORECASE)
    
    def replace_match(match):
        w = match.group(0).lower()
        expanded = CONTRACTIONS_MAP.get(w, w)
        if match.group(0).istitle():
            return expanded.capitalize()
        return expanded

    return pattern.sub(replace_match, text)


@dataclass
class SentenceSpan:
    """Represents a sentence with text, lowercase text, and original character offsets."""
    text: str
    lower_text: str
    start_char: int
    end_char: int


@dataclass
class PreprocessedDocument:
    """Container for preprocessed review text preserving offsets and sentence boundaries."""
    raw_text: str
    clean_text: str
    clean_text_lower: str
    sentences: List[SentenceSpan]


def preprocess_review(
    raw_text: str,
    spacy_model: Optional[spacy.language.Language] = None,
) -> PreprocessedDocument:
    """Preprocess review:
    1. Clean HTML, PII, and excessive whitespace.
    2. Split into sentences while preserving character offsets mapped to clean_text.
    3. Generate lowercase copy for matching while retaining original text for display.
    """
    cleaned = clean_text(raw_text)
    lower_copy = cleaned.lower()

    if not cleaned:
        return PreprocessedDocument(
            raw_text=raw_text,
            clean_text="",
            clean_text_lower="",
            sentences=[],
        )

    sentences = []
    if spacy_model is not None:
        doc = spacy_model(cleaned)
        for sent in doc.sents:
            s_text = sent.text.strip()
            if s_text:
                # Find start index of stripped sentence within original span
                leading_ws = len(sent.text) - len(sent.text.lstrip())
                trailing_ws = len(sent.text) - len(sent.text.rstrip())
                s_start = sent.start_char + leading_ws
                s_end = sent.end_char - trailing_ws
                sentences.append(SentenceSpan(
                    text=s_text,
                    lower_text=s_text.lower(),
                    start_char=s_start,
                    end_char=s_end,
                ))
    else:
        # Fallback simple regex sentence split with character offsets
        for match in re.finditer(r"[^.!?]+[.!?]*", cleaned):
            m_text = match.group(0).strip()
            if m_text:
                leading_ws = len(match.group(0)) - len(match.group(0).lstrip())
                trailing_ws = len(match.group(0)) - len(match.group(0).rstrip())
                s_start = match.start() + leading_ws
                s_end = match.end() - trailing_ws
                sentences.append(SentenceSpan(
                    text=m_text,
                    lower_text=m_text.lower(),
                    start_char=s_start,
                    end_char=s_end,
                ))

    return PreprocessedDocument(
        raw_text=raw_text,
        clean_text=cleaned,
        clean_text_lower=lower_copy,
        sentences=sentences,
    )
