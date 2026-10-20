"""Build a committed demo sample dataset (< 20 MB) with a few thousand reviews across top products."""

import json
import random
from pathlib import Path
from typing import List, Dict, Any
from collections import Counter, defaultdict

from data.scripts.download_amazon import load_amazon, PRODUCT_NAMES

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEMO_SAMPLE_FILE = BASE_DIR / "data" / "demo_sample.json"

# Fixed seed for deterministic sampling and reproducibility (Rule 9)
RANDOM_SEED = 42

# Select 15 top products with clear identities
CORE_PRODUCTS = [
    "B005SUHPO6",  # OtterBox Commuter Case
    "B0042FV2SI",  # Acase Dual Layer Case
    "B008OHNZI0",  # Tech Armor Screen Protector
    "B009RXU59C",  # Anker 24W Dual-Port USB Wall Charger
    "B000S5Q9CA",  # Universal Micro USB Car Charger
    "B007FHX9OK",  # Hyperion Extended Battery 3800mAh
    "B0073FCPSK",  # Anker Astro Mini 3000mAh Power Bank
    "B008DJIIG8",  # Kensington Protective Bumper
    "B0088LYCZC",  # Samsung OEM Micro USB Data Cable
    "B0015RB39O",  # Motorola Original Vehicle Power Adapter
    "B0090YGJ4I",  # i-Blason Armorbox Case
    "B007FXMOV8",  # Fintie Premium Vegan Leather Folio Case
    "B009A5204K",  # Spigen Ultra Thin Slim Armor Case
    "B00BT7RAPG",  # Maxboost 3.1A USB Car Charger
    "B0088U4YAG",  # Anker SlimTalk 3200mAh Battery Pack
]


def build_demo_sample(
    max_reviews_per_product: int = 250,
    seed: int = RANDOM_SEED,
) -> List[Dict[str, Any]]:
    """Sample reviews deterministically to create a compact, balanced demo dataset (< 20 MB)."""
    random.seed(seed)
    all_reviews = load_amazon()

    # Group reviews by product
    by_product = defaultdict(list)
    for r in all_reviews:
        pid = r.get("product_id")
        if pid in CORE_PRODUCTS:
            by_product[pid].append(r)

    sampled_reviews = []
    for pid in CORE_PRODUCTS:
        reviews = by_product[pid]
        if not reviews:
            continue

        # Stratified sampling across ratings to ensure healthy presence of negative & positive aspects
        by_rating = defaultdict(list)
        for r in reviews:
            by_rating[r["rating"]].append(r)

        product_sampled = []
        # Target per rating: ensure at least 20% negative/mixed (1-3 stars) if available
        for rating in [1, 2, 3, 4, 5]:
            rating_pool = by_rating[rating]
            random.shuffle(rating_pool)
            # Take proportional sample
            quota = max(15, int(max_reviews_per_product * (len(rating_pool) / len(reviews))))
            product_sampled.extend(rating_pool[:quota])

        # If below target, fill with remaining randomly
        if len(product_sampled) < max_reviews_per_product:
            remaining = [r for r in reviews if r not in product_sampled]
            random.shuffle(remaining)
            needed = max_reviews_per_product - len(product_sampled)
            product_sampled.extend(remaining[:needed])
        elif len(product_sampled) > max_reviews_per_product:
            random.shuffle(product_sampled)
            product_sampled = product_sampled[:max_reviews_per_product]

        sampled_reviews.extend(product_sampled)
        print(f"Sampled {len(product_sampled)} reviews for product {pid} ({PRODUCT_NAMES.get(pid, pid)})")

    # Sort deterministically by product_id and review_id
    sampled_reviews.sort(key=lambda x: (x["product_id"], x["review_id"]))

    DEMO_SAMPLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DEMO_SAMPLE_FILE, "w", encoding="utf-8") as f:
        json.dump(sampled_reviews, f, indent=2, ensure_ascii=False)

    size_mb = DEMO_SAMPLE_FILE.stat().st_size / (1024 * 1024)
    print(f"\nDemo sample successfully built:")
    print(f"- Total reviews: {len(sampled_reviews)}")
    print(f"- Total products: {len(CORE_PRODUCTS)}")
    print(f"- File size: {size_mb:.2f} MB (Constraint: < 20 MB)")
    assert size_mb < 20.0, f"Error: Demo sample size ({size_mb:.2f} MB) exceeds 20 MB limit!"

    return sampled_reviews


def load_demo_sample() -> List[Dict[str, Any]]:
    """Load the committed demo sample dataset."""
    if not DEMO_SAMPLE_FILE.exists():
        build_demo_sample()
    with open(DEMO_SAMPLE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    build_demo_sample()
