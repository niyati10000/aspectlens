"""Compute and print statistical distributions for datasets (demo sample, Amazon, SemEval)."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Ensure stdout handles UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEMO_SAMPLE_FILE = BASE_DIR / "data" / "demo_sample.json"
PROCESSED_AMAZON_FILE = BASE_DIR / "data" / "processed_amazon.json"
PROCESSED_SEMEVAL_FILE = BASE_DIR / "data" / "processed_semeval.json"


def compute_and_print_stats(dataset_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute and display detailed dataset statistics."""
    total_reviews = len(records)
    print("\n" + "=" * 70)
    print(f" DATASET STATISTICS: {dataset_name.upper()} (Total Reviews: {total_reviews:,})")
    print("=" * 70)

    if total_reviews == 0:
        print("Dataset is empty.")
        return {}

    # 1. Rating distribution
    rating_counts = Counter()
    has_ratings = False
    for r in records:
        rating = r.get("rating")
        if rating is not None:
            has_ratings = True
            rating_counts[rating] += 1

    print("\n1. RATING DISTRIBUTION:")
    if has_ratings:
        print(f"   {'Stars':<8} | {'Count':<10} | {'Percentage':<12}")
        print("   " + "-" * 34)
        for star in sorted(rating_counts.keys(), reverse=True):
            count = rating_counts[star]
            pct = (count / total_reviews) * 100
            bar = "*" * star + " " + "#" * int(pct / 5)
            count_str = f"{count:,}"
            print(f"   {star:<8} | {count_str:<10} | {pct:>6.2f}%  {bar}")
    else:
        print("   No star ratings available in this dataset (e.g., SemEval benchmark).")

    # 2. Review Length Analysis (characters and words)
    char_lengths = [len(r.get("text", "")) for r in records]
    word_lengths = [len(r.get("text", "").split()) for r in records]

    avg_chars = sum(char_lengths) / total_reviews
    avg_words = sum(word_lengths) / total_reviews
    min_words = min(word_lengths)
    max_words = max(word_lengths)

    print("\n2. REVIEW LENGTH STATISTICS:")
    print(f"   Average Characters per Review : {avg_chars:,.1f}")
    print(f"   Average Words per Review      : {avg_words:,.1f}")
    print(f"   Min Words / Max Words         : {min_words} / {max_words:,}")

    # 3. Reviews per Product
    product_records = defaultdict(list)
    product_names = {}
    for r in records:
        pid = r.get("product_id", "unknown")
        product_records[pid].append(r)
        if "product_name" in r:
            product_names[pid] = r["product_name"]

    print(f"\n3. REVIEWS PER PRODUCT ({len(product_records)} unique products):")
    print(f"   {'Product ID':<16} | {'Reviews':<9} | {'Avg Rating':<12} | {'Product Name'}")
    print("   " + "-" * 75)

    sorted_products = sorted(product_records.items(), key=lambda x: len(x[1]), reverse=True)
    for pid, p_reviews in sorted_products[:30]:
        count = len(p_reviews)
        ratings = [r["rating"] for r in p_reviews if r.get("rating") is not None]
        avg_r_str = f"{sum(ratings) / len(ratings):.2f} / 5" if ratings else "N/A"
        name = product_names.get(pid, pid)[:35]
        count_str = f"{count:,}"
        print(f"   {pid:<16} | {count_str:<9} | {avg_r_str:<12} | {name}")

    if len(sorted_products) > 30:
        print(f"   ... and {len(sorted_products) - 30} more products.")

    # 4. Aspect counts if SemEval
    if records and "aspect_terms" in records[0]:
        total_aspects = sum(len(r.get("aspect_terms", [])) for r in records)
        polarities = Counter()
        for r in records:
            for a in r.get("aspect_terms", []):
                polarities[a.get("polarity", "unknown")] += 1
        print(f"\n4. SEMEVAL ASPECT ANNOTATIONS (Total aspect mentions: {total_aspects:,}):")
        for pol, p_count in polarities.most_common():
            pct = (p_count / total_aspects) * 100
            print(f"   {pol.capitalize():<12} : {p_count:,} ({pct:.1f}%)")

    print("\n" + "=" * 70 + "\n")
    return {
        "total_reviews": total_reviews,
        "avg_words": avg_words,
        "avg_chars": avg_chars,
        "product_count": len(product_records),
    }


def main():
    parser = argparse.ArgumentParser(description="AspectLens dataset statistics runner.")
    parser.add_argument(
        "--dataset",
        choices=["demo", "amazon", "semeval", "all"],
        default="demo",
        help="Target dataset to inspect (default: demo)",
    )
    args = parser.parse_args()

    targets = []
    if args.dataset in ["demo", "all"] and DEMO_SAMPLE_FILE.exists():
        targets.append(("Demo Sample Dataset", DEMO_SAMPLE_FILE))
    if args.dataset in ["amazon", "all"] and PROCESSED_AMAZON_FILE.exists():
        targets.append(("Processed Amazon Full Sample", PROCESSED_AMAZON_FILE))
    if args.dataset in ["semeval", "all"] and PROCESSED_SEMEVAL_FILE.exists():
        targets.append(("SemEval-2014 Task 4 Combined", PROCESSED_SEMEVAL_FILE))

    if not targets:
        print(f"No processed files found for dataset choice: {args.dataset}")
        print("Run download_semeval.py, download_amazon.py, and build_demo_sample.py first.")
        return

    for label, path in targets:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        compute_and_print_stats(label, data)


if __name__ == "__main__":
    main()
