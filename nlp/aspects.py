"""Aspect candidate extraction and filtering.

Implements three switchable extraction methods:
1. NLTK RegexpParser (NP: {<DT>?<JJ>*<NN.*>+})
2. spaCy Noun Chunks
3. spaCy Dependency Rules (subject + acomp, amod + noun)

Includes generic-noun blacklist filtering and per-product frequency thresholding.
"""

from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Tuple
from collections import Counter
import re
import nltk
from nltk.tokenize import TreebankWordTokenizer
import spacy

# Generic noun blacklist as specified in BRAIN.md Rule 3
GENERIC_NOUN_BLACKLIST: Set[str] = {
    "thing", "things",
    "product", "products",
    "item", "items",
    "one", "ones",
    "time", "times",
    "day", "days",
    "way", "ways",
    "lot", "lots",
    "bit", "bits",
    "stuff",
    "something", "anything", "everything", "nothing",
    "someone", "anyone", "everyone", "nobody",
    "part", "parts",
    "use", "uses",
    "year", "years", "month", "months", "week", "weeks",
    "kind", "kinds", "sort", "sorts", "type", "types",
    "deal", "deals",
    "value", "purchase", "order",
}

# Pronouns that should never be aspect candidates
PRONOUNS_BLACKLIST: Set[str] = {
    "i", "me", "my", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "who", "whom", "whose", "which", "what",
    "this", "that", "these", "those",
}

DETERMINERS_AND_ARTICLES: Set[str] = {
    "the", "a", "an", "this", "that", "these", "those",
    "my", "your", "his", "her", "its", "our", "their",
    "all", "some", "any", "every", "each", "both", "such",
}

# Evaluative opinion adjectives to optionally strip from leading chunks
EVALUATIVE_ADJECTIVES: Set[str] = {
    "great", "good", "bad", "terrible", "horrible", "awesome", "amazing",
    "excellent", "poor", "mediocre", "stunning", "fantastic", "wonderful",
    "superb", "disappointing", "impressive", "decent", "nice", "subpar",
}

NP_CHUNK_GRAMMAR = r"NP: {<DT>?<JJ>*<NN.*>+}"


@dataclass
class AspectCandidate:
    """Represents an extracted aspect candidate with exact character offsets in review text."""
    term: str              # Original surface text slice (e.g. "Battery life")
    lemma: str             # Normalized lowercase lemma (e.g. "battery life")
    char_start: int        # Character start offset in review text
    char_end: int          # Character end offset in review text
    extractor: str         # "nltk_regex" | "spacy_chunks" | "spacy_deps"
    head_noun: str         # Core head noun for filtering


_SPACY_MODEL = None


def get_spacy_model() -> spacy.language.Language:
    """Lazy loader for spaCy en_core_web_sm model."""
    global _SPACY_MODEL
    if _SPACY_MODEL is None:
        _SPACY_MODEL = spacy.load("en_core_web_sm")
    return _SPACY_MODEL


def is_generic_noun(term_or_head: str) -> bool:
    """Check if a candidate or its head noun matches the generic blacklist or pronoun list."""
    clean = term_or_head.strip().lower()
    if clean in GENERIC_NOUN_BLACKLIST or clean in PRONOUNS_BLACKLIST:
        return True
    words = clean.split()
    # Single-word checks
    if len(words) == 1 and (words[0] in GENERIC_NOUN_BLACKLIST or words[0] in PRONOUNS_BLACKLIST):
        return True
    # Head word checks (e.g. "awesome item", "great thing")
    if words[-1] in GENERIC_NOUN_BLACKLIST or words[-1] in PRONOUNS_BLACKLIST:
        if len(words) <= 2:
            return True
    return False


def _clean_candidate_span(
    text: str,
    start: int,
    end: int,
    extractor_name: str,
    nlp_doc: Optional[spacy.tokens.Doc] = None,
    strip_evaluative: bool = False,
) -> Optional[AspectCandidate]:
    """Validate, trim determiners/pronouns, and construct an AspectCandidate ensuring exact character slice."""
    if start < 0 or end > len(text) or start >= end:
        return None

    raw_slice = text[start:end]
    stripped = raw_slice.strip()
    if not stripped or len(stripped) < 2:
        return None

    leading_ws = len(raw_slice) - len(raw_slice.lstrip())
    trailing_ws = len(raw_slice) - len(raw_slice.rstrip())
    adj_start = start + leading_ws
    adj_end = end - trailing_ws

    term = text[adj_start:adj_end]

    # Trim leading determiners/articles (e.g. "the battery life" -> "battery life")
    words = term.split()
    while words and (words[0].lower() in DETERMINERS_AND_ARTICLES or words[0].lower() in PRONOUNS_BLACKLIST):
        drop_word = words.pop(0)
        advance = len(drop_word)
        while adj_start + advance < adj_end and text[adj_start + advance].isspace():
            advance += 1
        adj_start += advance
        term = text[adj_start:adj_end].strip()

    # Optionally trim leading purely evaluative adjectives (e.g. "awesome item" -> "item", "great screen" -> "screen")
    if strip_evaluative and len(words) > 1:
        while words and words[0].lower() in EVALUATIVE_ADJECTIVES:
            drop_word = words.pop(0)
            advance = len(drop_word)
            while adj_start + advance < adj_end and text[adj_start + advance].isspace():
                advance += 1
            adj_start += advance
            term = text[adj_start:adj_end].strip()

    if not term or len(term) < 2 or term.isnumeric():
        return None

    if term.lower() in PRONOUNS_BLACKLIST:
        return None

    # Determine lemma and head noun using spaCy doc or fallback
    if nlp_doc is not None:
        span_tokens = [t for t in nlp_doc if t.idx >= adj_start and (t.idx + len(t)) <= adj_end]
        if span_tokens:
            head = span_tokens[-1].lemma_.lower()
            lemma = " ".join(t.lemma_.lower() for t in span_tokens if t.pos_ not in ("DET", "PUNCT", "PRON"))
        else:
            head = term.split()[-1].lower()
            lemma = term.lower()
    else:
        head = term.split()[-1].lower()
        lemma = term.lower()

    if not lemma or is_generic_noun(head) or is_generic_noun(lemma):
        return None

    # Invariant: text[adj_start:adj_end] == term
    assert text[adj_start:adj_end] == term, f"Offset mismatch: '{text[adj_start:adj_end]}' != '{term}'"

    return AspectCandidate(
        term=term,
        lemma=lemma,
        char_start=adj_start,
        char_end=adj_end,
        extractor=extractor_name,
        head_noun=head,
    )


# ----------------------------------------------------------------------
# Extractor 1: NLTK RegexpParser
# ----------------------------------------------------------------------
def extract_aspects_nltk(text: str, nlp_spacy: Optional[spacy.language.Language] = None) -> List[AspectCandidate]:
    """Extractor 1: NLTK RegexpParser with grammar NP: {<DT>?<JJ>*<NN.*>+}."""
    if not text or not text.strip():
        return []

    nlp = nlp_spacy or get_spacy_model()
    spacy_doc = nlp(text)

    tokenizer = TreebankWordTokenizer()
    spans = list(tokenizer.span_tokenize(text))
    tokens = [text[s:e] for s, e in spans]
    if not tokens:
        return []

    pos_tags = nltk.pos_tag(tokens)
    parser = nltk.RegexpParser(NP_CHUNK_GRAMMAR)
    tree = parser.parse(pos_tags)

    candidates: List[AspectCandidate] = []
    token_idx = 0

    for subtree in tree:
        if isinstance(subtree, nltk.Tree) and subtree.label() == "NP":
            chunk_len = len(subtree.leaves())
            start_token = token_idx
            end_token = token_idx + chunk_len - 1

            start_char = spans[start_token][0]
            end_char = spans[end_token][1]

            cand = _clean_candidate_span(text, start_char, end_char, "nltk_regex", spacy_doc)
            if cand:
                candidates.append(cand)
            token_idx += chunk_len
        else:
            token_idx += 1

    return _deduplicate_candidates(candidates)


# ----------------------------------------------------------------------
# Extractor 2: spaCy Noun Chunks
# ----------------------------------------------------------------------
def extract_aspects_spacy_chunks(text: str, nlp_spacy: Optional[spacy.language.Language] = None) -> List[AspectCandidate]:
    """Extractor 2: spaCy noun chunks extraction with determiner & pronoun stripping."""
    if not text or not text.strip():
        return []

    nlp = nlp_spacy or get_spacy_model()
    doc = nlp(text)

    candidates: List[AspectCandidate] = []
    for chunk in doc.noun_chunks:
        # Strip leading evaluative adjectives to extract the core aspect
        cand = _clean_candidate_span(text, chunk.start_char, chunk.end_char, "spacy_chunks", doc, strip_evaluative=True)
        if cand:
            candidates.append(cand)

    return _deduplicate_candidates(candidates)


# ----------------------------------------------------------------------
# Extractor 3: spaCy Dependency Rules
# ----------------------------------------------------------------------
def extract_aspects_spacy_deps(text: str, nlp_spacy: Optional[spacy.language.Language] = None) -> List[AspectCandidate]:
    """Extractor 3: spaCy syntactic dependency rules:
    - Subject + Adjective Complement (nsubj/nsubjpass with copula or acomp/attr)
    - Adjective Modifier + Noun (amod modifying noun head)
    - Prepositional objects or direct objects modifying aspect structures
    """
    if not text or not text.strip():
        return []

    nlp = nlp_spacy or get_spacy_model()
    doc = nlp(text)

    candidates: List[AspectCandidate] = []

    for token in doc:
        # Rule 3a: Subject with adjective complement or copular predicate
        if token.dep_ in ("nsubj", "nsubjpass") and token.pos_ in ("NOUN", "PROPN"):
            head = token.head
            has_acomp = any(c.dep_ in ("acomp", "attr", "amod", "oprd") for c in head.children)
            is_copula = head.pos_ in ("ADJ", "VERB", "AUX")
            if has_acomp or is_copula:
                span_tokens = _expand_noun_phrase(token)
                start_char = span_tokens[0].idx
                end_char = span_tokens[-1].idx + len(span_tokens[-1])
                cand = _clean_candidate_span(text, start_char, end_char, "spacy_deps", doc)
                if cand:
                    candidates.append(cand)

        # Rule 3b: Adjective Modifier + Noun
        elif token.dep_ == "amod" and token.head.pos_ in ("NOUN", "PROPN"):
            head_noun = token.head
            span_tokens = _expand_noun_phrase(head_noun)
            start_char = span_tokens[0].idx
            end_char = span_tokens[-1].idx + len(span_tokens[-1])
            cand = _clean_candidate_span(text, start_char, end_char, "spacy_deps", doc)
            if cand:
                candidates.append(cand)

        # Rule 3c: Direct objects of verbs with modifiers or prepositional objects
        elif token.dep_ in ("dobj", "pobj") and token.pos_ in ("NOUN", "PROPN"):
            if any(c.dep_ in ("amod", "compound") for c in token.children):
                span_tokens = _expand_noun_phrase(token)
                start_char = span_tokens[0].idx
                end_char = span_tokens[-1].idx + len(span_tokens[-1])
                cand = _clean_candidate_span(text, start_char, end_char, "spacy_deps", doc)
                if cand:
                    candidates.append(cand)

    return _deduplicate_candidates(candidates)


def _expand_noun_phrase(noun_token: spacy.tokens.Token) -> List[spacy.tokens.Token]:
    """Expand a noun token to include adjacent compound tokens and nominal modifiers."""
    tokens = [noun_token]
    for left in noun_token.lefts:
        # Include compound nouns and domain-descriptive modifiers (e.g. Sound quality, charging speed)
        if left.dep_ in ("compound", "compound:prt") or (
            left.dep_ == "amod" and left.text.lower() not in EVALUATIVE_ADJECTIVES
        ):
            tokens.append(left)
    for right in noun_token.rights:
        if right.dep_ in ("compound", "compound:prt"):
            tokens.append(right)
    tokens.sort(key=lambda t: t.i)
    return tokens


def _deduplicate_candidates(candidates: List[AspectCandidate]) -> List[AspectCandidate]:
    """Deduplicate candidates by overlapping span, keeping the more specific span."""
    if not candidates:
        return []

    sorted_cands = sorted(candidates, key=lambda c: (-(c.char_end - c.char_start), c.char_start))
    kept: List[AspectCandidate] = []

    for cand in sorted_cands:
        overlap = False
        for k in kept:
            if max(cand.char_start, k.char_start) < min(cand.char_end, k.char_end):
                overlap = True
                break
        if not overlap:
            kept.append(cand)

    kept.sort(key=lambda c: c.char_start)
    return kept


# ----------------------------------------------------------------------
# Frequency Filtering across Product Reviews (Rule 4)
# ----------------------------------------------------------------------
def filter_candidates_by_frequency(
    review_candidates_list: List[List[AspectCandidate]],
    min_freq: int = 5,
) -> List[List[AspectCandidate]]:
    """Filter candidates across a product's reviews: keep only candidates appearing in >= min_freq reviews."""
    if min_freq <= 1:
        return review_candidates_list

    lemma_review_counts = Counter()
    for review_cands in review_candidates_list:
        distinct_lemmas = set(c.lemma for c in review_cands)
        for lemma in distinct_lemmas:
            lemma_review_counts[lemma] += 1

    filtered_reviews = []
    for review_cands in review_candidates_list:
        kept = [c for c in review_cands if lemma_review_counts[c.lemma] >= min_freq]
        filtered_reviews.append(kept)

    return filtered_reviews


# ----------------------------------------------------------------------
# Master Extraction Dispatcher
# ----------------------------------------------------------------------
def extract_aspects(
    text: str,
    method: str = "spacy_chunks",
    min_freq: int = 1,
    product_reviews: Optional[List[str]] = None,
    nlp_spacy: Optional[spacy.language.Language] = None,
) -> List[AspectCandidate]:
    """Extract aspect candidates using the selected switchable extractor."""
    if not text or not text.strip():
        return []

    nlp = nlp_spacy or get_spacy_model()

    if method == "nltk_regex":
        cands = extract_aspects_nltk(text, nlp)
    elif method == "spacy_chunks":
        cands = extract_aspects_spacy_chunks(text, nlp)
    elif method == "spacy_deps":
        cands = extract_aspects_spacy_deps(text, nlp)
    elif method == "all":
        c1 = extract_aspects_nltk(text, nlp)
        c2 = extract_aspects_spacy_chunks(text, nlp)
        c3 = extract_aspects_spacy_deps(text, nlp)
        cands = _deduplicate_candidates(c1 + c2 + c3)
    else:
        raise ValueError(
            f"Unknown aspect extraction method: '{method}'. Choose from 'nltk_regex', 'spacy_chunks', 'spacy_deps', 'all'."
        )

    if product_reviews and min_freq > 1:
        corpus_cands = [extract_aspects(r, method=method, min_freq=1, nlp_spacy=nlp) for r in product_reviews]
        filtered_corpus = filter_candidates_by_frequency(corpus_cands + [cands], min_freq=min_freq)
        return filtered_corpus[-1]

    return cands
