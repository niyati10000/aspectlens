"""System Latency and Throughput Benchmark.

Measures per-review latency and overall throughput (reviews/second) across:
1. Full VADER-based pipeline (lightweight production mode)
2. Full Transformer-based pipeline (high-accuracy deep learning mode)
3. Component-level timing breakdown (preprocessing, candidate extraction, grouping, opinion linking, scoring)
4. Percentile distributions (mean, p50, p90, p99)

Saves results to:
- eval/results/latency_benchmark.json
- eval/results/latency_benchmark.csv
"""

import json
import csv
import time
import logging
from pathlib import Path
from typing import List, Dict, Any
import numpy as np

from nlp.preprocess import clean_text
from nlp.aspects import extract_aspects, get_spacy_model
from nlp.grouping import AspectGrouper
from nlp.opinions import extract_opinions_for_aspect, split_into_clauses
from nlp.sentiment import VADERScorer, TransformerScorer
from nlp.pipeline import analyze_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "demo_sample.json"
RESULTS_DIR = BASE_DIR / "eval" / "results"


def run_latency_benchmark(
    data_path: Path = DATA_PATH,
    results_dir: Path = RESULTS_DIR,
    sample_size: int = 100,
) -> Dict[str, Any]:
    """Execute latency profiling across VADER and Transformer ABSA configurations."""
    logger.info("Loading review sample for latency benchmark from %s", data_path)
    with open(data_path, "r", encoding="utf-8") as f:
        all_reviews = json.load(f)

    # Select representative sample of non-trivial reviews
    valid_texts = [r["text"] for r in all_reviews if r.get("text") and 40 <= len(r["text"]) <= 800]
    sample_texts = valid_texts[:sample_size]

    logger.info("Benchmarking on %d sample reviews (avg len: %.1f chars)", len(sample_texts), np.mean([len(t) for t in sample_texts]))

    nlp = get_spacy_model()
    grouper = AspectGrouper()
    vader = VADERScorer()
    transformer = TransformerScorer()

    # Warmup runs
    logger.info("Warming up models...")
    _ = analyze_review("Great battery life and clear screen.", scorer="vader", spacy_nlp=nlp, grouper=grouper)
    _ = analyze_review("Great battery life and clear screen.", scorer="transformer", spacy_nlp=nlp, grouper=grouper)

    # 1. Benchmark VADER Pipeline
    logger.info("Profiling VADER Pipeline on %d reviews...", len(sample_texts))
    vader_latencies: List[float] = []
    t_start_vader = time.perf_counter()

    for text in sample_texts:
        t0 = time.perf_counter()
        _ = analyze_review(text, scorer="vader", spacy_nlp=nlp, grouper=grouper)
        vader_latencies.append((time.perf_counter() - t0) * 1000)

    total_vader_time = time.perf_counter() - t_start_vader
    vader_throughput = len(sample_texts) / total_vader_time if total_vader_time > 0 else 0

    # 2. Benchmark Transformer Pipeline
    # Test on a 30-review subset for transformer to balance benchmark speed
    tr_sample = sample_texts[:30]
    logger.info("Profiling Transformer Pipeline on %d reviews...", len(tr_sample))
    transformer_latencies: List[float] = []
    t_start_tr = time.perf_counter()

    for text in tr_sample:
        t0 = time.perf_counter()
        _ = analyze_review(text, scorer="transformer", spacy_nlp=nlp, grouper=grouper)
        transformer_latencies.append((time.perf_counter() - t0) * 1000)

    total_tr_time = time.perf_counter() - t_start_tr
    transformer_throughput = len(tr_sample) / total_tr_time if total_tr_time > 0 else 0

    # 3. Component Breakdown (measured over 50 reviews)
    breakdown_sample = sample_texts[:50]
    logger.info("Measuring granular component breakdown on %d reviews...", len(breakdown_sample))

    t_preprocess: List[float] = []
    t_extraction: List[float] = []
    t_grouping: List[float] = []
    t_opinions: List[float] = []
    t_vader_scoring: List[float] = []

    for text in breakdown_sample:
        # Preprocessing
        t0 = time.perf_counter()
        cleaned = clean_text(text)
        t_preprocess.append((time.perf_counter() - t0) * 1000)

        # Extraction
        t0 = time.perf_counter()
        candidates = extract_aspects(cleaned, method="spacy_chunks", nlp_spacy=nlp)
        t_extraction.append((time.perf_counter() - t0) * 1000)

        # Parse & Clauses
        doc = nlp(cleaned)
        clauses = split_into_clauses(doc)

        # Grouping & Opinions & Scoring
        for c in candidates:
            t0 = time.perf_counter()
            canon, _, _ = grouper.group_aspect(c.term)
            t_grouping.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            opinion_words, clause_text = extract_opinions_for_aspect(doc, c.char_start, c.char_end, clauses)
            t_opinions.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            _ = vader.score(clause_text, c.term, opinion_words)
            t_vader_scoring.append((time.perf_counter() - t0) * 1000)

    def stats(arr: List[float]) -> Dict[str, float]:
        if not arr:
            return {"mean": 0, "p50": 0, "p90": 0, "p99": 0, "min": 0, "max": 0}
        return {
            "mean_ms": round(float(np.mean(arr)), 2),
            "p50_ms": round(float(np.percentile(arr, 50)), 2),
            "p90_ms": round(float(np.percentile(arr, 90)), 2),
            "p99_ms": round(float(np.percentile(arr, 99)), 2),
            "min_ms": round(float(np.min(arr)), 2),
            "max_ms": round(float(np.max(arr)), 2),
        }

    output_payload = {
        "benchmark": "system_latency_and_throughput",
        "sample_size": len(sample_texts),
        "configurations": [
            {
                "config": "VADER Full Pipeline",
                "scorer": "vader",
                "extractor": "spacy_chunks",
                "throughput_reviews_per_sec": round(vader_throughput, 2),
                **stats(vader_latencies),
            },
            {
                "config": "Transformer Full Pipeline",
                "scorer": "transformer",
                "extractor": "spacy_chunks",
                "throughput_reviews_per_sec": round(transformer_throughput, 2),
                **stats(transformer_latencies),
            },
        ],
        "component_breakdown": {
            "preprocessing": stats(t_preprocess),
            "candidate_extraction": stats(t_extraction),
            "canonical_grouping_per_candidate": stats(t_grouping),
            "opinion_association_per_candidate": stats(t_opinions),
            "vader_scoring_per_candidate": stats(t_vader_scoring),
        },
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "latency_benchmark.json"
    csv_path = results_dir / "latency_benchmark.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    logger.info("Saved JSON results to %s", json_path)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["config", "throughput_reviews_per_sec", "mean_ms", "p50_ms", "p90_ms", "p99_ms", "min_ms", "max_ms"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in output_payload["configurations"]:
            writer.writerow({
                "config": c["config"],
                "throughput_reviews_per_sec": c["throughput_reviews_per_sec"],
                "mean_ms": c["mean_ms"],
                "p50_ms": c["p50_ms"],
                "p90_ms": c["p90_ms"],
                "p99_ms": c["p99_ms"],
                "min_ms": c["min_ms"],
                "max_ms": c["max_ms"],
            })
    logger.info("Saved CSV results to %s", csv_path)

    return output_payload


if __name__ == "__main__":
    results = run_latency_benchmark()
    print("\n=== Latency & Throughput Benchmark ===")
    for c in results["configurations"]:
        print(f"[{c['config']}] Mean: {c['mean_ms']} ms | Throughput: {c['throughput_reviews_per_sec']} reviews/s")
