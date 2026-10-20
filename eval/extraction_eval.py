"""Aspect candidate extraction ablation benchmark on SemEval-2014 Task 4.

Evaluates four progressive pipeline ablations:
1. chunks_only: spaCy noun chunks with generic noun & pronoun filtering.
2. chunks_plus_deps: noun chunks combined with dependency parse rules.
3. chunks_plus_deps_plus_freq: previous ablation with corpus-level frequency filtering (min_freq >= 2).
4. full_pipeline: frequency-filtered candidates mapped through canonical AspectGrouper.

Computes exact match and token overlap Precision, Recall, and F1.
Saves results to eval/results/extraction_ablation.json and extraction_ablation.csv.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any

from nlp.aspects import (
    AspectCandidate,
    _deduplicate_candidates,
    extract_aspects_spacy_deps,
    filter_candidates_by_frequency,
    get_spacy_model,
)
from nlp.grouping import AspectGrouper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "processed_semeval.json"
RESULTS_DIR = BASE_DIR / "eval" / "results"


def compute_prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Calculate Precision, Recall, and F1 score."""
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0
    return round(p, 4), round(r, 4), round(f1, 4)


def evaluate_extraction_lists(
    predicted_lists: list[list[str]],
    gold_lists: list[list[str]],
) -> dict[str, Any]:
    """Evaluate exact string matches between predicted candidate lemmas and gold terms."""
    tp, fp, fn = 0, 0, 0

    for preds, golds in zip(predicted_lists, gold_lists):
        p_set = set(p.strip().lower() for p in preds if p.strip())
        g_set = set(g.strip().lower() for g in golds if g.strip())

        matched_tp = len(p_set & g_set)
        tp += matched_tp
        fp += len(p_set - g_set)
        fn += len(g_set - p_set)

    p, r, f1 = compute_prf(tp, fp, fn)
    return {
        "precision": p,
        "recall": r,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "total_gold": sum(
            len(set(g.strip().lower() for g in g_list if g.strip())) for g_list in gold_lists
        ),
        "total_predicted": sum(
            len(set(p.strip().lower() for p in p_list if p.strip())) for p_list in predicted_lists
        ),
    }


def evaluate_overlap_lists(
    predicted_lists: list[list[str]],
    gold_lists: list[list[str]],
) -> dict[str, Any]:
    """Evaluate token-overlap matches (partial credit for boundary variations)."""
    tp, fp, fn = 0, 0, 0

    for preds, golds in zip(predicted_lists, gold_lists):
        p_set = set(p.strip().lower() for p in preds if p.strip())
        g_set = set(g.strip().lower() for g in golds if g.strip())

        matched_gold = set()
        matched_pred = set()

        for g in g_set:
            g_tokens = set(g.split())
            for p in p_set:
                p_tokens = set(p.split())
                if g == p or (g_tokens & p_tokens):
                    matched_gold.add(g)
                    matched_pred.add(p)

        tp += len(matched_gold)
        fn += len(g_set - matched_gold)
        fp += len(p_set - matched_pred)

    prec, rec, f1_val = compute_prf(tp, fp, fn)
    return {
        "precision_overlap": prec,
        "recall_overlap": rec,
        "f1_overlap": f1_val,
    }


def run_extraction_evaluation(
    data_path: Path = DATA_PATH,
    results_dir: Path = RESULTS_DIR,
    sample_limit: int = 0,
) -> dict[str, Any]:
    """Run four extraction ablations over the SemEval test set and save results."""
    logger.info("Loading SemEval data from %s", data_path)
    with open(data_path, encoding="utf-8") as f:
        all_data = json.load(f)

    # Use identical official test split
    test_docs = [row for row in all_data if row.get("split") == "test"]
    if sample_limit > 0:
        test_docs = test_docs[:sample_limit]

    logger.info("Evaluating on %d SemEval test sentences", len(test_docs))

    nlp = get_spacy_model()
    grouper = AspectGrouper()

    # Pre-parse spaCy docs to avoid redundant parsing across ablations
    logger.info("Pre-parsing test texts with spaCy en_core_web_sm...")
    spacy_docs = [nlp(row["text"]) for row in test_docs]

    gold_terms_per_doc = [
        [t["term"].strip().lower() for t in row.get("aspect_terms", [])] for row in test_docs
    ]

    # --- Ablation 1: Chunks only ---
    logger.info("Running Ablation 1: Chunks only...")
    chunks_cands_raw: list[list[AspectCandidate]] = []
    for doc in spacy_docs:
        cands = []
        for chunk in doc.noun_chunks:
            from nlp.aspects import _clean_candidate_span

            cand = _clean_candidate_span(
                doc.text,
                chunk.start_char,
                chunk.end_char,
                "spacy_chunks",
                doc,
                strip_evaluative=True,
            )
            if cand:
                cands.append(cand)
        chunks_cands_raw.append(_deduplicate_candidates(cands))

    chunks_preds = [[c.lemma.lower().strip() for c in doc_cands] for doc_cands in chunks_cands_raw]
    res1_exact = evaluate_extraction_lists(chunks_preds, gold_terms_per_doc)
    res1_overlap = evaluate_overlap_lists(chunks_preds, gold_terms_per_doc)

    # --- Ablation 2: Chunks + Dependency Rules ---
    logger.info("Running Ablation 2: Chunks + Dependency Rules...")
    deps_cands_raw: list[list[AspectCandidate]] = []
    for doc, c_cands in zip(spacy_docs, chunks_cands_raw):
        d_cands = extract_aspects_spacy_deps(doc.text, nlp_spacy=nlp)
        merged = _deduplicate_candidates(c_cands + d_cands)
        deps_cands_raw.append(merged)

    deps_preds = [[c.lemma.lower().strip() for c in doc_cands] for doc_cands in deps_cands_raw]
    res2_exact = evaluate_extraction_lists(deps_preds, gold_terms_per_doc)
    res2_overlap = evaluate_overlap_lists(deps_preds, gold_terms_per_doc)

    # --- Ablation 3: Chunks + Dependency Rules + Frequency Filter ---
    logger.info("Running Ablation 3: Chunks + Dependency Rules + Frequency Filter (min_freq=2)...")
    freq_filtered_cands = filter_candidates_by_frequency(deps_cands_raw, min_freq=2)
    freq_preds = [[c.lemma.lower().strip() for c in doc_cands] for doc_cands in freq_filtered_cands]
    res3_exact = evaluate_extraction_lists(freq_preds, gold_terms_per_doc)
    res3_overlap = evaluate_overlap_lists(freq_preds, gold_terms_per_doc)

    # --- Ablation 4: Full Pipeline (+ Canonical Grouping) ---
    logger.info("Running Ablation 4: Full Pipeline (+ Canonical Grouping)...")
    # For grouping ablation, map candidate terms through AspectGrouper
    grouped_preds = []
    for doc_cands in freq_filtered_cands:
        doc_grouped = []
        for c in doc_cands:
            canon, _, _ = grouper.group_aspect(c.term)
            doc_grouped.append(canon.lower().strip())
        grouped_preds.append(doc_grouped)

    res4_exact = evaluate_extraction_lists(grouped_preds, gold_terms_per_doc)
    res4_overlap = evaluate_overlap_lists(grouped_preds, gold_terms_per_doc)

    ablation_results = [
        {
            "ablation": "1. Chunks Only",
            "description": "spaCy noun chunks with blacklist filtering",
            "exact_precision": res1_exact["precision"],
            "exact_recall": res1_exact["recall"],
            "exact_f1": res1_exact["f1"],
            "overlap_f1": res1_overlap["f1_overlap"],
            "tp": res1_exact["tp"],
            "fp": res1_exact["fp"],
            "fn": res1_exact["fn"],
        },
        {
            "ablation": "2. Chunks + Dependency Rules",
            "description": "Noun chunks combined with syntactic subject/amod rules",
            "exact_precision": res2_exact["precision"],
            "exact_recall": res2_exact["recall"],
            "exact_f1": res2_exact["f1"],
            "overlap_f1": res2_overlap["f1_overlap"],
            "tp": res2_exact["tp"],
            "fp": res2_exact["fp"],
            "fn": res2_exact["fn"],
        },
        {
            "ablation": "3. Chunks + Deps + Frequency Filter",
            "description": "Candidate pruning requiring corpus frequency >= 2",
            "exact_precision": res3_exact["precision"],
            "exact_recall": res3_exact["recall"],
            "exact_f1": res3_exact["f1"],
            "overlap_f1": res3_overlap["f1_overlap"],
            "tp": res3_exact["tp"],
            "fp": res3_exact["fp"],
            "fn": res3_exact["fn"],
        },
        {
            "ablation": "4. Full Pipeline (+ Grouping)",
            "description": "Canonical aspect normalization via lexicon, WordNet & SBERT",
            "exact_precision": res4_exact["precision"],
            "exact_recall": res4_exact["recall"],
            "exact_f1": res4_exact["f1"],
            "overlap_f1": res4_overlap["f1_overlap"],
            "tp": res4_exact["tp"],
            "fp": res4_exact["fp"],
            "fn": res4_exact["fn"],
        },
    ]

    output_payload = {
        "benchmark": "aspect_extraction_ablation",
        "dataset": "SemEval-2014 Task 4 (Laptops & Restaurants Test)",
        "test_sentences": len(test_docs),
        "total_gold_aspects": sum(len(g) for g in gold_terms_per_doc),
        "ablations": ablation_results,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "extraction_ablation.json"
    csv_path = results_dir / "extraction_ablation.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    logger.info("Saved JSON results to %s", json_path)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "ablation",
            "description",
            "exact_precision",
            "exact_recall",
            "exact_f1",
            "overlap_f1",
            "tp",
            "fp",
            "fn",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in ablation_results:
            writer.writerow(row)
    logger.info("Saved CSV results to %s", csv_path)

    return output_payload


if __name__ == "__main__":
    results = run_extraction_evaluation()
    print("\n=== SemEval-2014 Aspect Extraction Ablation Results ===")
    for row in results["ablations"]:
        print(
            f"[{row['ablation']}] P: {row['exact_precision']:.4f} | R: {row['exact_recall']:.4f} | Exact F1: {row['exact_f1']:.4f} | Overlap F1: {row['overlap_f1']:.4f}"
        )
