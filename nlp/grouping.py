"""Aspect canonical grouping module.

Combines three switchable methods:
1. Seed lexicon exact/keyphrase matching (data/seed_lexicon.json) - Priority 1 (wins on conflicts).
2. WordNet taxonomic synonyms and hypernyms (nltk.corpus.wordnet).
3. Sentence-Transformers cosine similarity and AgglomerativeClustering (all-MiniLM-L6-v2).

Includes embedding caching and individual ablation toggles.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
from nltk.corpus import wordnet as wn
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering

from app.config import settings

_TRANSFORMER_MODEL = None


def get_embedding_model() -> SentenceTransformer:
    """Lazy loader for sentence-transformers all-MiniLM-L6-v2 model."""
    global _TRANSFORMER_MODEL
    if _TRANSFORMER_MODEL is None:
        _TRANSFORMER_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _TRANSFORMER_MODEL


class AspectGrouper:
    """Groups candidate aspect terms into canonical aspects using Seed Lexicon, WordNet, and MiniLM Embeddings."""

    def __init__(self, lexicon_path: Path | None = None):
        self.lexicon_path = lexicon_path or settings.SEED_LEXICON_PATH
        self.canonical_aspects: dict[str, dict[str, Any]] = {}
        self.keyword_to_canonical: dict[str, str] = {}
        self.embedding_cache: dict[str, np.ndarray] = {}
        self.canonical_embeddings: dict[str, np.ndarray] = {}
        self.canonical_list: list[str] = []

        self.reload_lexicon()

    def reload_lexicon(self) -> None:
        """Reload seed lexicon from JSON without requiring code changes."""
        if not self.lexicon_path.exists():
            return

        with open(self.lexicon_path, encoding="utf-8") as f:
            data = json.load(f)

        self.canonical_aspects = data.get("canonical_aspects", {})
        self.keyword_to_canonical.clear()

        # Build reverse lookup map
        for canonical, info in self.canonical_aspects.items():
            self.keyword_to_canonical[canonical.lower()] = canonical
            for kw in info.get("keywords", []):
                self.keyword_to_canonical[kw.lower()] = canonical

        self.canonical_list = list(self.canonical_aspects.keys())
        self._init_canonical_embeddings()

    def _init_canonical_embeddings(self) -> None:
        """Precompute normalized centroid embeddings for canonical aspects."""
        if not self.canonical_list:
            return

        model = get_embedding_model()
        for c in self.canonical_list:
            kws = self.canonical_aspects[c].get("keywords", [])[:6]
            terms_to_encode = [c] + kws
            embs = model.encode(terms_to_encode, normalize_embeddings=True, show_progress_bar=False)
            centroid = np.mean(embs, axis=0)
            centroid = centroid / np.linalg.norm(centroid)
            self.canonical_embeddings[c] = centroid

    def get_embedding(self, text: str) -> np.ndarray:
        """Fetch normalized embedding from cache or encode via model."""
        clean = text.strip().lower()
        if clean in self.embedding_cache:
            return self.embedding_cache[clean]

        model = get_embedding_model()
        emb = model.encode([clean], normalize_embeddings=True, show_progress_bar=False)[0]
        self.embedding_cache[clean] = emb
        return emb

    def get_embeddings_batch(self, texts: list[str]) -> np.ndarray:
        """Batch encode with caching."""
        needed = []
        indices = []
        for i, t in enumerate(texts):
            clean = t.strip().lower()
            if clean not in self.embedding_cache:
                needed.append(clean)
                indices.append(i)

        if needed:
            model = get_embedding_model()
            new_embs = model.encode(needed, normalize_embeddings=True, show_progress_bar=False)
            for clean, emb in zip(needed, new_embs):
                self.embedding_cache[clean] = emb

        result = [self.embedding_cache[t.strip().lower()] for t in texts]
        return np.array(result)

    # ------------------------------------------------------------------
    # Tool 1: Seed Lexicon Matching (Rule: Wins on conflicts)
    # ------------------------------------------------------------------
    def match_seed_lexicon(self, candidate_term: str) -> str | None:
        """Match candidate against seed lexicon keywords (exact or substring)."""
        term_lower = candidate_term.strip().lower()

        # 1. Exact match on term or lemma
        if term_lower in self.keyword_to_canonical:
            return self.keyword_to_canonical[term_lower]

        # 2. Check if a multi-word keyword is fully contained in term, or term in keyword
        for kw, canonical in self.keyword_to_canonical.items():
            if len(kw.split()) > 1 and kw in term_lower:
                return canonical
            if len(term_lower.split()) > 1 and term_lower in kw:
                return canonical

        return None

    # ------------------------------------------------------------------
    # Tool 2: WordNet Synonyms & Hypernyms
    # ------------------------------------------------------------------
    def match_wordnet(self, candidate_term: str) -> str | None:
        """Match candidate using WordNet primary sense synonyms and immediate hypernyms."""
        words = candidate_term.strip().lower().split()
        if not words:
            return None

        # Prioritize head noun (last word)
        target_words = [words[-1]] + words[:-1]

        for word in target_words:
            synsets = wn.synsets(word, pos=wn.NOUN)
            if not synsets:
                continue

            # Check primary sense (synsets[0] is the most frequent English sense)
            primary_sense = synsets[0]

            # 1. Direct lemmas (synonyms of primary sense)
            for lemma in primary_sense.lemmas():
                lemma_name = lemma.name().lower().replace("_", " ")
                if lemma_name in self.keyword_to_canonical:
                    return self.keyword_to_canonical[lemma_name]

            # 2. Immediate hypernyms of primary sense (against canonical names)
            for hyper in primary_sense.hypernyms():
                for h_lemma in hyper.lemmas():
                    h_name = h_lemma.name().lower().replace("_", " ")
                    if h_name in self.keyword_to_canonical:
                        # Match only if hypernym is a canonical aspect name to prevent drift
                        canon = self.keyword_to_canonical[h_name]
                        if canon.lower() == h_name:
                            return canon

        return None

    # ------------------------------------------------------------------
    # Tool 3: MiniLM Cosine Similarity Matching
    # ------------------------------------------------------------------
    def match_embeddings(
        self,
        candidate_term: str,
        threshold: float = 0.50,
    ) -> tuple[str | None, float]:
        """Match candidate against canonical aspect embeddings using cosine similarity."""
        if not self.canonical_embeddings:
            return None, 0.0

        cand_emb = self.get_embedding(candidate_term)

        best_score = -1.0
        best_canonical = None

        for canonical, c_emb in self.canonical_embeddings.items():
            score = float(np.dot(cand_emb, c_emb))
            if score > best_score:
                best_score = score
                best_canonical = canonical

        if best_score >= threshold and best_canonical is not None:
            return best_canonical, best_score

        return None, best_score

    # ------------------------------------------------------------------
    # Unified Grouping Function (Ablation-ready)
    # ------------------------------------------------------------------
    def group_aspect(
        self,
        candidate_term: str,
        use_seed: bool = True,
        use_wordnet: bool = True,
        use_embeddings: bool = True,
        similarity_threshold: float = 0.50,
    ) -> tuple[str, str, float]:
        """Map a candidate aspect term to its canonical aspect name.

        Returns:
            (canonical_name, origin, confidence)
            origin is one of: 'seed', 'wordnet', 'embedding', 'unmatched'
        """
        # 1. Seed Lexicon (Priority 1: wins on conflicts)
        if use_seed:
            seed_match = self.match_seed_lexicon(candidate_term)
            if seed_match:
                return seed_match, "seed", 1.0

        # 2. WordNet Synonyms & Hypernyms
        if use_wordnet:
            wn_match = self.match_wordnet(candidate_term)
            if wn_match:
                return wn_match, "wordnet", 0.90

        # 3. MiniLM Embeddings Cosine Similarity
        if use_embeddings:
            emb_match, score = self.match_embeddings(candidate_term, threshold=similarity_threshold)
            if emb_match:
                return emb_match, "embedding", round(score, 3)

        # Fallback: Unmatched
        return candidate_term.title(), "unmatched", 0.0

    # ------------------------------------------------------------------
    # Agglomerative Clustering for Emergent Aspects
    # ------------------------------------------------------------------
    def cluster_unmatched(
        self,
        unmatched_terms: list[str],
        distance_threshold: float = 0.35,
    ) -> dict[str, list[str]]:
        """Cluster terms that were not matched to any seed canonical aspect using AgglomerativeClustering."""
        if not unmatched_terms:
            return {}
        if len(unmatched_terms) == 1:
            return {unmatched_terms[0].title(): unmatched_terms}

        unique_terms = list(set(unmatched_terms))
        embs = self.get_embeddings_batch(unique_terms)

        clustering = AgglomerativeClustering(
            metric="cosine",
            linkage="average",
            distance_threshold=distance_threshold,
            n_clusters=None,
        )
        labels = clustering.fit_predict(embs)

        clusters: dict[str, list[str]] = {}
        for label_id in set(labels):
            members = [unique_terms[i] for i, lbl in enumerate(labels) if lbl == label_id]
            # Medoid calculation: member closest to the cluster center
            cluster_embs = [embs[i] for i, lbl in enumerate(labels) if lbl == label_id]
            centroid = np.mean(cluster_embs, axis=0)
            centroid = centroid / np.linalg.norm(centroid)
            sims = [np.dot(e, centroid) for e in cluster_embs]
            medoid_term = members[int(np.argmax(sims))]
            cluster_name = medoid_term.title()
            clusters[cluster_name] = members

        return clusters


_DEFAULT_GROUPER = None


def get_aspect_grouper() -> AspectGrouper:
    """Lazy loader for default AspectGrouper instance."""
    global _DEFAULT_GROUPER
    if _DEFAULT_GROUPER is None:
        _DEFAULT_GROUPER = AspectGrouper()
    return _DEFAULT_GROUPER


def group_aspect_term(
    term: str,
    use_seed: bool = True,
    use_wordnet: bool = True,
    use_embeddings: bool = True,
    similarity_threshold: float = 0.50,
) -> tuple[str, str, float]:
    """Convenience function to group an aspect term."""
    grouper = get_aspect_grouper()
    return grouper.group_aspect(
        term,
        use_seed=use_seed,
        use_wordnet=use_wordnet,
        use_embeddings=use_embeddings,
        similarity_threshold=similarity_threshold,
    )
