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

import sys
import time
import json
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import numpy as np
import torch

from eval.extraction_eval import run_extraction_evaluation
from eval.sentiment_eval import run_sentiment_evaluation
from eval.baseline_tfidf import run_baseline_evaluation
from eval.amazon_value import run_amazon_value_evaluation
from eval.latency import run_latency_benchmark
from eval.error_analysis import run_error_analysis

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


def run_all_benchmarks() -> Dict[str, Any]:
    """Execute all benchmarks and compile summary metrics."""
    t_start = time.perf_counter()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print_ascii_header("AspectLens Comprehensive NLP Evaluation Pipeline")
    print(f"Start Time (UTC): {datetime.now(timezone.utc).isoformat()}")
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
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_runtime_seconds": round(total_duration, 1),
        "aspect_extraction": {
            "best_ablation": max(ext_results["ablations"], key=lambda x: x["exact_f1"])["ablation"],
            "best_exact_f1": max(ext_results["ablations"], key=lambda x: x["exact_f1"])["exact_f1"],
            "best_overlap_f1": max(ext_results["ablations"], key=lambda x: x["overlap_f1"])["overlap_f1"],
            "ablations": ext_results["ablations"],
        },
        "aspect_sentiment": {
            "vader": next(r for r in sent_results["results"] if r["scorer"] == "vader"),
            "transformer": next(r for r in sent_results["results"] if r["scorer"] == "transformer"),
            "baseline": base_results["baseline"],
            "winner": "transformer" if next(r for r in sent_results["results"] if r["scorer"] == "transformer")["macro_f1"] > next(r for r in sent_results["results"] if r["scorer"] == "vader")["macro_f1"] else "vader",
        },
        "amazon_value": {
            "high_star_with_negative_aspect_pct": amz_results["metrics"]["high_star_reviews"]["share_pct"],
            "low_star_with_positive_aspect_pct": amz_results["metrics"]["low_star_reviews"]["share_pct"],
        },
        "system_performance": {
            "vader_mean_latency_ms": next(c for c in lat_results["configurations"] if "VADER" in c["config"])["mean_ms"],
            "vader_throughput_rps": next(c for c in lat_results["configurations"] if "VADER" in c["config"])["throughput_reviews_per_sec"],
            "transformer_mean_latency_ms": next(c for c in lat_results["configurations"] if "Transformer" in c["config"])["mean_ms"],
            "transformer_throughput_rps": next(c for c in lat_results["configurations"] if "Transformer" in c["config"])["throughput_reviews_per_sec"],
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
    print(f"{'Ablation':<36} | {'Exact P':<8} | {'Exact R':<8} | {'Exact F1':<8} | {'Overlap F1':<10}")
    print("-" * 78)
    for a in ext_results["ablations"]:
        print(f"{a['ablation']:<36} | {a['exact_precision']:<8.4f} | {a['exact_recall']:<8.4f} | {a['exact_f1']:<8.4f} | {a['overlap_f1']:<10.4f}")

    print("\n--- Aspect Sentiment Classification ---")
    print(f"{'Model / Scorer':<36} | {'Accuracy':<10} | {'Macro-F1':<10} | {'Pos F1':<8} | {'Neg F1':<8}")
    print("-" * 78)
    v_item = summary["aspect_sentiment"]["vader"]
    t_item = summary["aspect_sentiment"]["transformer"]
    b_item = summary["aspect_sentiment"]["baseline"]
    print(f"{'TF-IDF Whole-Review Baseline':<36} | {b_item['accuracy']:<10.4f} | {b_item['macro_f1']:<10.4f} | {b_item['per_class']['positive']['f1']:<8.4f} | {b_item['per_class']['negative']['f1']:<8.4f}")
    print(f"{'AspectLens VADER Scorer':<36} | {v_item['accuracy']:<10.4f} | {v_item['macro_f1']:<10.4f} | {v_item['per_class']['positive']['f1']:<8.4f} | {v_item['per_class']['negative']['f1']:<8.4f}")
    print(f"{'AspectLens RoBERTa Transformer':<36} | {t_item['accuracy']:<10.4f} | {t_item['macro_f1']:<10.4f} | {t_item['per_class']['positive']['f1']:<8.4f} | {t_item['per_class']['negative']['f1']:<8.4f}")

    print("\n--- Amazon Mixed-Sentiment Value Discovery ---")
    print(f"  * High-Star (4-5 stars) Reviews with >= 1 Negative Aspect: {summary['amazon_value']['high_star_with_negative_aspect_pct']}% (Hidden Critical Issues)")
    print(f"  * Low-Star (1-2 stars) Reviews with >= 1 Positive Aspect:  {summary['amazon_value']['low_star_with_positive_aspect_pct']}% (Hidden Redeeming Qualities)")

    print("\n--- System Throughput & Latency ---")
    print(f"  * VADER Pipeline:       {summary['system_performance']['vader_mean_latency_ms']} ms/review ({summary['system_performance']['vader_throughput_rps']} reviews/sec)")
    print(f"  * Transformer Pipeline: {summary['system_performance']['transformer_mean_latency_ms']} ms/review ({summary['system_performance']['transformer_throughput_rps']} reviews/sec)")

    print("\n--- Error Analysis Breakdown (N = {}) ---".format(summary["error_analysis"]["total_curated_examples"]))
    for cat, cnt in summary["error_analysis"]["category_breakdown"].items():
        print(f"  * {cat:<24}: {cnt} examples")

    print("\n" + "=" * 78)
    print("  ALL BENCHMARKS EXECUTED SUCCESSFULLY AND ARTIFACTS PERSISTED TO eval/results/")
    print("=" * 78 + "\n")

    return summary


if __name__ == "__main__":
    run_all_benchmarks()
