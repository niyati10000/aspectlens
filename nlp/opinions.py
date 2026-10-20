"""Clause-scoped opinion word association, contrast boundary splitting, and negation handling.

Adheres strictly to BRAIN.md Non-negotiable NLP Rules:
- Rule 5: Dependency arcs first -> fallback window <= 5 tokens within the same clause.
  Never cross a contrast word (but, however, although, though, yet).
- Rule 6: No opinion word found -> return empty list (sentiment scorer assigns neutral, low confidence).
- Rule 7: Handle negation ('not good', 'never arrived') and intensifiers ('too', 'very', 'extremely') explicitly.
"""

from typing import List, Dict, Tuple, Optional, Set
import re
import spacy
from spacy.tokens import Doc, Token

from nlp.aspects import get_spacy_model

# Contrast conjunctions and transition words that form strict sentiment clause boundaries
CONTRAST_WORDS: Set[str] = {
    "but",
    "however",
    "although",
    "though",
    "yet",
    "nevertheless",
    "nonetheless",
    "whereas",
    "while",
}

# Negation words to attach to opinion modifiers and verbs
NEGATION_WORDS: Set[str] = {
    "not",
    "n't",
    "never",
    "no",
    "neither",
    "nor",
    "hardly",
    "barely",
    "scarcely",
    "seldom",
    "rarely",
}

# Intensifiers and degree adverbs
INTENSIFIERS: Set[str] = {
    "too",
    "very",
    "extremely",
    "really",
    "so",
    "super",
    "highly",
    "exceptionally",
    "incredibly",
    "terribly",
    "immensely",
    "quite",
    "pretty",
    "fairly",
    "somewhat",
}

# Common transaction or neutral functional verbs that should NOT be treated as evaluative opinions
NEUTRAL_VERBS: Set[str] = {
    "buy",
    "bought",
    "purchase",
    "purchased",
    "order",
    "ordered",
    "receive",
    "received",
    "get",
    "got",
    "gotten",
    "have",
    "had",
    "use",
    "used",
    "own",
    "owned",
    "take",
    "took",
    "taken",
    "put",
    "find",
    "found",
    "see",
    "saw",
    "seen",
    "give",
    "gave",
    "given",
    "come",
    "came",
    "go",
    "went",
    "gone",
    "be",
    "is",
    "was",
    "are",
    "were",
    "do",
    "did",
    "done",
}

# Known evaluative or domain-specific sentiment terms (adjectives, adverbs, verbs)
EVALUATIVE_TERMS: Set[str] = {
    "amazing", "great", "good", "excellent", "awesome", "fantastic", "wonderful",
    "superb", "impressive", "decent", "nice", "fine", "reliable", "sturdy",
    "fast", "responsive", "crisp", "clear", "bright", "sharp", "smooth",
    "bad", "terrible", "horrible", "awful", "poor", "mediocre", "subpar",
    "disappointing", "slow", "sluggish", "laggy", "late", "delayed",
    "overpriced", "expensive", "costly", "cheap", "damaged", "broken",
    "defective", "scratched", "flimsy", "heavy", "noisy", "loud", "faint",
    "dull", "dim", "blurry", "hot", "warm", "dead", "unusable", "unresponsive",
    "love", "like", "recommend", "enjoy", "prefer", "praise",
    "hate", "dislike", "regret", "fail", "failed", "crash", "crashed",
    "lag", "lags", "lagged", "drain", "drains", "drained", "break", "broke",
    "scratch", "scratched", "suck", "sucks", "sucked", "burn", "burned",
    "work", "worked", "function", "functioned",
}


def split_into_clauses(doc: Doc) -> List[Tuple[int, int, str]]:
    """Split a spaCy Doc into clause spans (start_token_idx, end_token_idx, clause_text).
    
    Strictly splits at contrast words (but, however, although, though, yet, etc.)
    and clause-bounding punctuation (;, :, ., !, ?).
    """
    if len(doc) == 0:
        return []

    boundaries = [0]
    for i, token in enumerate(doc):
        # 1. Punctuation boundaries
        if token.text in {";", ":", ".", "!", "?"} and i + 1 < len(doc):
            boundaries.append(i + 1)
        # 2. Contrast word boundaries
        elif token.lower_ in CONTRAST_WORDS:
            if i > 0 and i not in boundaries:
                boundaries.append(i)
            next_idx = i + 1
            if next_idx < len(doc) and doc[next_idx].text == ",":
                next_idx += 1
            if next_idx < len(doc) and next_idx not in boundaries:
                boundaries.append(next_idx)

    boundaries = sorted(list(set(boundaries)))
    if boundaries[-1] != len(doc):
        boundaries.append(len(doc))

    clauses: List[Tuple[int, int, str]] = []
    for s, e in zip(boundaries[:-1], boundaries[1:]):
        span_text = doc[s:e].text.strip()
        cleaned_text = span_text.lstrip(",;:.- ").rstrip(",;:.- ").strip()
        if cleaned_text:
            clauses.append((s, e, cleaned_text))

    if not clauses:
        clauses.append((0, len(doc), doc.text.strip()))

    return clauses


def get_clause_for_aspect(
    doc: Doc,
    aspect_start_char: int,
    aspect_end_char: int,
    clauses: Optional[List[Tuple[int, int, str]]] = None,
) -> Tuple[int, int, str]:
    """Identify the exact clause span corresponding to an aspect's character span."""
    if clauses is None:
        clauses = split_into_clauses(doc)

    aspect_token_indices = [
        t.i for t in doc if t.idx >= aspect_start_char and (t.idx + len(t)) <= aspect_end_char
    ]
    if not aspect_token_indices:
        aspect_token_indices = [min(doc, key=lambda t: abs(t.idx - aspect_start_char)).i]

    mid_token = aspect_token_indices[len(aspect_token_indices) // 2]
    for s, e, text in clauses:
        if s <= mid_token < e:
            return s, e, text

    return 0, len(doc), doc.text.strip()


def extract_opinions_for_aspect(
    doc: Doc,
    aspect_start_char: int,
    aspect_end_char: int,
    clauses: Optional[List[Tuple[int, int, str]]] = None,
) -> Tuple[List[str], str]:
    """Find opinion words associated with an aspect candidate in a review.
    
    Follows Non-negotiable Rules:
    1. Scope strictly within the aspect's clause; never cross a contrast word.
    2. Dependency arcs first (nsubj + acomp/attr, amod, dobj).
    3. Fallback window <= 5 tokens inside the same clause.
    4. Handle negation ('not', 'never', 'n't') and intensifiers ('too', 'very', 'extremely').
    5. Return empty list if no opinion word is found.
    
    Returns:
        (opinion_words: List[str], clause_text: str)
    """
    if clauses is None:
        clauses = split_into_clauses(doc)

    clause_start_tok, clause_end_tok, clause_text = get_clause_for_aspect(
        doc, aspect_start_char, aspect_end_char, clauses
    )
    clause_token_indices = set(range(clause_start_tok, clause_end_tok))

    aspect_tokens = [
        t for t in doc if t.idx >= aspect_start_char and (t.idx + len(t)) <= aspect_end_char
    ]
    if not aspect_tokens:
        return [], clause_text

    opinion_phrases: List[str] = []

    def build_opinion_phrase(
        word_token: Token,
        extra_neg_word: Optional[str] = None,
    ) -> Optional[str]:
        """Construct an opinion phrase attaching negation and intensifier modifiers."""
        # Reject non-evaluative neutral transaction verbs
        if word_token.pos_ in ("VERB", "AUX") and word_token.lemma_.lower() in NEUTRAL_VERBS:
            return None

        # Check for negation and intensifier in word's syntactic children
        neg_word: Optional[str] = extra_neg_word
        intensifier_word: Optional[str] = None

        for child in word_token.children:
            if child.i in clause_token_indices:
                if child.dep_ == "neg" or child.lower_ in NEGATION_WORDS:
                    neg_word = child.text.lower()
                elif child.dep_ == "advmod" and child.lower_ in INTENSIFIERS:
                    intensifier_word = child.text.lower()

        # Check immediate preceding token in clause if not already captured
        prev_idx = word_token.i - 1
        if prev_idx in clause_token_indices:
            prev_tok = doc[prev_idx]
            if prev_tok.lower_ in NEGATION_WORDS and not neg_word:
                neg_word = prev_tok.text.lower()
            elif prev_tok.lower_ in INTENSIFIERS and not intensifier_word:
                intensifier_word = prev_tok.text.lower()

        # Also check two tokens back for negation preceding an intensifier (e.g. "not very good")
        prev2_idx = word_token.i - 2
        if prev2_idx in clause_token_indices and not neg_word:
            prev2_tok = doc[prev2_idx]
            if prev2_tok.lower_ in NEGATION_WORDS:
                neg_word = prev2_tok.text.lower()

        parts = []
        if neg_word:
            parts.append(neg_word)
        if intensifier_word:
            parts.append(intensifier_word)
        parts.append(word_token.text)
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Step 1: Dependency Relations First (Priority 1)
    # ------------------------------------------------------------------
    # 1a. Direct adjective modifier (amod) on aspect tokens
    for t in aspect_tokens:
        for child in t.children:
            if child.i in clause_token_indices and child.dep_ == "amod":
                phrase = build_opinion_phrase(child)
                if phrase:
                    opinion_phrases.append(phrase)

    # 1b. Aspect is subject (nsubj / nsubjpass) of predicate
    for t in aspect_tokens:
        if t.dep_ in ("nsubj", "nsubjpass"):
            pred = t.head
            if pred.i in clause_token_indices:
                # Find any negation attached directly to the predicate verb/copula
                pred_neg_word = None
                for c in pred.children:
                    if c.i in clause_token_indices and (c.dep_ == "neg" or c.lower_ in NEGATION_WORDS):
                        pred_neg_word = c.text.lower()

                # If predicate is an adjective itself
                if pred.pos_ in ("ADJ",):
                    phrase = build_opinion_phrase(pred, extra_neg_word=pred_neg_word)
                    if phrase:
                        opinion_phrases.append(phrase)

                # If predicate is a verb or auxiliary copula (is, was, feels, seems, runs)
                elif pred.pos_ in ("AUX", "VERB"):
                    found_complement = False
                    for child in pred.children:
                        if child.i in clause_token_indices and child.dep_ in ("acomp", "attr", "oprd", "advmod", "dobj"):
                            # Check if child is an adjective, opinion noun/adverb, or evaluative term
                            is_eval = (
                                child.pos_ in ("ADJ", "ADV")
                                or child.lower_ in EVALUATIVE_TERMS
                                or (child.pos_ == "NOUN" and child.dep_ in ("acomp", "attr"))
                            )
                            if is_eval:
                                phrase = build_opinion_phrase(child, extra_neg_word=pred_neg_word)
                                if phrase:
                                    opinion_phrases.append(phrase)
                                    found_complement = True
                                # Also check conjoined adjectives ("late and damaged")
                                for conj in child.conjuncts:
                                    if conj.i in clause_token_indices and (
                                        conj.pos_ in ("ADJ", "ADV") or conj.lower_ in EVALUATIVE_TERMS
                                    ):
                                        c_phrase = build_opinion_phrase(conj, extra_neg_word=pred_neg_word)
                                        if c_phrase:
                                            opinion_phrases.append(c_phrase)

                    # If no adjective complement was found, check if the verb itself is evaluative
                    if not found_complement and pred.lemma_.lower() not in NEUTRAL_VERBS:
                        is_eval_verb = (
                            pred.lower_ in EVALUATIVE_TERMS
                            or pred_neg_word is not None
                            or any(c.dep_ == "advmod" for c in pred.children if c.i in clause_token_indices)
                        )
                        if is_eval_verb:
                            phrase = build_opinion_phrase(pred, extra_neg_word=pred_neg_word)
                            if phrase:
                                opinion_phrases.append(phrase)

    # 1c. Aspect is direct object or prepositional object of a verb ("I love the camera")
    for t in aspect_tokens:
        if t.dep_ in ("dobj", "pobj"):
            verb = t.head
            if verb.i in clause_token_indices and verb.pos_ in ("VERB",):
                if verb.lemma_.lower() not in NEUTRAL_VERBS:
                    verb_neg_word = None
                    for c in verb.children:
                        if c.i in clause_token_indices and (c.dep_ == "neg" or c.lower_ in NEGATION_WORDS):
                            verb_neg_word = c.text.lower()
                    phrase = build_opinion_phrase(verb, extra_neg_word=verb_neg_word)
                    if phrase:
                        opinion_phrases.append(phrase)

    # ------------------------------------------------------------------
    # Step 2: Fallback Window <= 5 tokens in the SAME clause
    # ------------------------------------------------------------------
    if not opinion_phrases:
        aspect_indices = set(t.i for t in aspect_tokens)
        min_tok = min(aspect_indices)
        max_tok = max(aspect_indices)

        candidates_in_window: List[Tuple[int, Token]] = []
        for i in sorted(clause_token_indices):
            if i in aspect_indices:
                continue
            dist = min(abs(i - min_tok), abs(i - max_tok))
            if dist <= 5:
                tok = doc[i]
                is_eval_candidate = (
                    tok.pos_ in ("ADJ",)
                    or tok.lower_ in EVALUATIVE_TERMS
                ) and tok.lemma_.lower() not in NEUTRAL_VERBS
                if is_eval_candidate:
                    candidates_in_window.append((dist, tok))

        if candidates_in_window:
            # Pick the closest evaluative word in the window
            candidates_in_window.sort(key=lambda x: x[0])
            best_tok = candidates_in_window[0][1]
            phrase = build_opinion_phrase(best_tok)
            if phrase:
                opinion_phrases.append(phrase)

    # Clean, normalize whitespace, and deduplicate
    dedup: List[str] = []
    for op in opinion_phrases:
        clean_op = " ".join(op.strip().split())
        if clean_op and clean_op not in dedup:
            dedup.append(clean_op)

    return dedup, clause_text
