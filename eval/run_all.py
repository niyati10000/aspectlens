"""Master Evaluation Pipeline for AspectLens.

Executes all evaluation benchmarks in a single reproducible command:
1. Extraction Ablation (SemEval-2014 Task 4) -> extraction_ablation.json / .csv
2. Aspect Sentiment Benchmark (VADER vs RoBERTa vs FineTuned) -> sentiment_benchmark.json / .csv
3. Baseline TF-IDF + Logistic Regression -> baseline_comparison.json / .csv
4. Amazon Mixed-Sentiment Value Discovery -> amazon_mixed_sentiment.json / .csv
5. System Latency & Throughput Benchmark -> latency_benchmark.json / .csv
6. Categorized Error Analysis (>= 50 examples) -> error_analysis.json / .csv
7. Master Summary Metrics -> summary_metrics.json

Usage:
    python -m eval.run_all
"""

import json
import logging
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from eval.amazon_value import run_amazon_value_evaluation
from eval.baseline_tfidf import run_baseline_evaluation
from eval.error_analysis import run_error_analysis
from eval.extraction_eval import run_extraction_evaluation
from eval.latency import run_latency_benchmark
from eval.sentiment_eval import run_sentiment_evaluation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "eval" / "results"


def set_seed(seed: int = 42) -> None:
    """Set global random seeds for deterministic evaluation reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    logger.info("Random seeds set to %d across Python, NumPy, and PyTorch.", seed)


def print_ascii_header(title: str) -> None:
    """Print standard visual section divider."""
    print("\n" + "=" * 78)
    print(f"  {title.upper()}")
    print("=" * 78)


def run_all_benchmarks() -> dict[str, Any]:
    """Execute all benchmarks and compile summary metrics."""
    t_start = time.perf_counter()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print_ascii_header("AspectLens Comprehensive NLP Evaluation Pipeline")
    print(f"Start Time (UTC): {datetime.now(UTC).isoformat()}")
    print(f"Results Directory: {RESULTS_DIR}")

    # Set seeds
    set_seed(42)

    # 1. Aspect Extraction Ablation
    print_ascii_header("1. Aspect Extraction Ablation Benchmark (SemEval-2014)")
    t0 = time.perf_counter()
    ext_results = run_extraction_evaluation(results_dir=RESULTS_DIR)
    print(f"Completed extraction ablations in {time.perf_counter() - t0:.1f}s")

    # 2. Aspect Sentiment Benchmark
    print_ascii_header("2. Aspect Sentiment Classification Benchmark")
    t0 = time.perf_counter()
    sent_results = run_sentiment_evaluation(results_dir=RESULTS_DIR)
    print(f"Completed sentiment evaluations in {time.perf_counter() - t0:.1f}s")

    # 3. TF-IDF + Logistic Regression Baseline
    print_ascii_header("3. TF-IDF Whole-Review Baseline Benchmark")
    t0 = time.perf_counter()
    base_results = run_baseline_evaluation(results_dir=RESULTS_DIR)
    print(f"Completed baseline benchmark in {time.perf_counter() - t0:.1f}s")

    # 4. Amazon Mixed-Sentiment Value Discovery
    print_ascii_header("4. Amazon Mixed-Sentiment Value Discovery")
    t0 = time.perf_counter()
    amz_results = run_amazon_value_evaluation(results_dir=RESULTS_DIR, sample_limit=800)
    print(f"Completed Amazon value benchmark in {time.perf_counter() - t0:.1f}s")

    # 5. System Latency and Throughput
    print_ascii_header("5. Latency & Throughput Benchmark")
    t0 = time.perf_counter()
    lat_results = run_latency_benchmark(results_dir=RESULTS_DIR, sample_size=80)
    print(f"Completed latency benchmark in {time.perf_counter() - t0:.1f}s")

    # 6. Categorized Error Analysis
    print_ascii_header("6. Linguistic Error Analysis (>= 50 Examples)")
    t0 = time.perf_counter()
    err_results = run_error_analysis(results_dir=RESULTS_DIR, target_count=60)
    print(f"Completed error analysis in {time.perf_counter() - t0:.1f}s")

    total_duration = time.perf_counter() - t_start

    # Compile Summary Metrics
    vader_metric = next(r for r in sent_results["results"] if r["scorer"] == "vader")
    transformer_metric = next(r for r in sent_results["results"] if r["scorer"] == "transformer")
    baseline_metric = base_results["baseline"]
    vader_lat = next(c for c in lat_results["configurations"] if "VADER" in c["config"])
    tr_lat = next(c for c in lat_results["configurations"] if "Transformer" in c["config"])

    summary: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_runtime_seconds": round(total_duration, 1),
        "aspect_extraction": {
            "best_ablation": max(ext_results["ablations"], key=lambda x: x["exact_f1"])["ablation"],
            "best_exact_f1": max(ext_results["ablations"], key=lambda x: x["exact_f1"])["exact_f1"],
            "best_overlap_f1": max(ext_results["ablations"], key=lambda x: x["overlap_f1"])["overlap_f1"],
            "ablations": ext_results["ablations"],
        },
        "aspect_sentiment": {
            "vader": vader_metric,
            "transformer": transformer_metric,
            "baseline": baseline_metric,
            "winner": "transformer" if transformer_metric["macro_f1"] > vader_metric["macro_f1"] else "vader",
        },
        "amazon_value": {
            "high_star_with_negative_aspect_pct": amz_results["metrics"]["high_star_reviews"]["share_pct"],
            "low_star_with_positive_aspect_pct": amz_results["metrics"]["low_star_reviews"]["share_pct"],
        },
        "system_performance": {
            "vader_mean_latency_ms": vader_lat["mean_ms"],
            "vader_throughput_rps": vader_lat["throughput_reviews_per_sec"],
            "transformer_mean_latency_ms": tr_lat["mean_ms"],
            "transformer_throughput_rps": tr_lat["throughput_reviews_per_sec"],
        },
        "error_analysis": {
            "total_curated_examples": err_results["total_examples_curated"],
            "category_breakdown": err_results["category_distribution"],
        },
    }

    summary_path = RESULTS_DIR / "summary_metrics.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info("Saved master summary metrics to %s", summary_path)

    # Print Final Summary Report
    print_ascii_header("AspectLens Benchmark Summary Report")
    print(f"Total Execution Time: {total_duration:.1f} seconds")
    print("\n--- Aspect Extraction Ablation (SemEval-2014) ---")
    print(
        f"{'Ablation':<36} | {'Exact P':<8} | {'Exact R':<8} | {'Exact F1':<8} | {'Overlap F1':<10}"
    )
    print("-" * 78)
    for a in ext_results["ablations"]:
        print(
            f"{a['ablation']:<36} | {a['exact_precision']:<8.4f} | {a['exact_recall']:<8.4f} | {a['exact_f1']:<8.4f} | {a['overlap_f1']:<10.4f}"
        )

    print("\n--- Aspect Sentiment Classification ---")
    print(
        f"{'Model / Scorer':<36} | {'Accuracy':<10} | {'Macro-F1':<10} | {'Pos F1':<8} | {'Neg F1':<8}"
    )
    print("-" * 78)
    print(
        f"{'TF-IDF Whole-Review Baseline':<36} | {baseline_metric['accuracy']:<10.4f} | {baseline_metric['macro_f1']:<10.4f} | {baseline_metric['per_class']['positive']['f1']:<8.4f} | {baseline_metric['per_class']['negative']['f1']:<8.4f}"
    )
    print(
        f"{'AspectLens VADER Scorer':<36} | {vader_metric['accuracy']:<10.4f} | {vader_metric['macro_f1']:<10.4f} | {vader_metric['per_class']['positive']['f1']:<8.4f} | {vader_metric['per_class']['negative']['f1']:<8.4f}"
    )
    print(
        f"{'AspectLens RoBERTa Transformer':<36} | {transformer_metric['accuracy']:<10.4f} | {transformer_metric['macro_f1']:<10.4f} | {transformer_metric['per_class']['positive']['f1']:<8.4f} | {transformer_metric['per_class']['negative']['f1']:<8.4f}"
    )

    print("\n--- Amazon Mixed-Sentiment Value Discovery ---")
    print(
        f"  * High-Star (4-5 stars) Reviews with >= 1 Negative Aspect: {amz_results['metrics']['high_star_reviews']['share_pct']}% (Hidden Critical Issues)"
    )
    print(
        f"  * Low-Star (1-2 stars) Reviews with >= 1 Positive Aspect:  {amz_results['metrics']['low_star_reviews']['share_pct']}% (Hidden Redeeming Qualities)"
    )

    print("\n--- System Throughput & Latency ---")
    print(
        f"  * VADER Pipeline:       {vader_lat['mean_ms']} ms/review ({vader_lat['throughput_reviews_per_sec']} reviews/sec)"
    )
    print(
        f"  * Transformer Pipeline: {tr_lat['mean_ms']} ms/review ({tr_lat['throughput_reviews_per_sec']} reviews/sec)"
    )

    print(
        "\n--- Error Analysis Breakdown (N = {}) ---".format(
            err_results["total_examples_curated"]
        )
    )
    for cat, cnt in err_results["category_distribution"].items():
        print(f"  * {cat:<24}: {cnt} examples")

    print("\n" + "=" * 78)
    print("  ALL BENCHMARKS EXECUTED SUCCESSFULLY AND ARTIFACTS PERSISTED TO eval/results/")
    print("=" * 78 + "\n")

    return summary


if __name__ == "__main__":
    run_all_benchmarks()
