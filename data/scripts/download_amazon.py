"""Download and parse Amazon review datasets into common review schema."""

import os
import gzip
import json
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import Counter

from nlp.preprocess import clean_text

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_AMAZON_FILE = BASE_DIR / "data" / "processed_amazon.json"

SNAP_URL = "https://snap.stanford.edu/data/amazon/productGraph/categoryFiles/reviews_Cell_Phones_and_Accessories_5.json.gz"
LOCAL_GZ = RAW_DIR / "reviews_Cell_Phones_and_Accessories_5.json.gz"

# Readable names for prominent ASINs in this dataset
PRODUCT_NAMES = {
    "B005SUHPO6": "OtterBox Commuter Case (Plum)",
    "B0042FV2SI": "Acase Super Tough Dual Layer Case",
    "B008OHNZI0": "Tech Armor HD Clear Screen Protector",
    "B009RXU59C": "Anker 24W Dual-Port USB Wall Charger",
    "B000S5Q9CA": "Universal Micro USB Car Charger",
    "B007FHX9OK": "Hyperion Extended Battery 3800mAh",
    "B0073FCPSK": "Anker Astro Mini 3000mAh Power Bank",
    "B008DJIIG8": "Kensington Protective Rubber Bumper",
    "B0088LYCZC": "Samsung OEM Micro USB Data Cable",
    "B0015RB39O": "Motorola Original Vehicle Power Adapter",
    "B0090YGJ4I": "i-Blason Armorbox Hybrid Protective Case",
    "B007FXMOV8": "Fintie Premium Vegan Leather Folio Case",
    "B009A5204K": "Spigen Ultra Thin Slim Armor Case",
    "B00BT7RAPG": "Maxboost 3.1A USB Car Charger",
    "B0088U4YAG": "Anker SlimTalk 3200mAh Battery Pack",
    "B005SUHRVC": "OtterBox Defender Series Rugged Case",
    "B008LFTCAK": "Plantronics Marque M155 Bluetooth Headset",
    "B00ANALDWQ": "Powergen 2.4A Dual USB Car Adapter",
    "B0052YFYFK": "Cimo Shock Absorbent Bumper Case",
    "B0059DLLJC": "iKross 3.5mm Stereo Audio Cable with Mic",
}


def download_snap_dataset() -> Path:
    """Download the SNAP Cell Phones 5-core gzip file if not already present."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if LOCAL_GZ.exists() and LOCAL_GZ.stat().st_size > 1000000:
        print(f"Dataset already exists: {LOCAL_GZ} ({LOCAL_GZ.stat().st_size} bytes)")
        return LOCAL_GZ

    print(f"Downloading SNAP Amazon Cell Phones dataset from {SNAP_URL}...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(SNAP_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp, open(LOCAL_GZ, "wb") as f:
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            print(f"Downloaded {downloaded / (1024*1024):.1f} / {total / (1024*1024):.1f} MB", end="\r")

    print(f"\nDownload complete: {LOCAL_GZ}")
    return LOCAL_GZ


def parse_amazon_reviews(
    target_reviews: int = 25000,
    top_n_products: int = 70,
    min_product_reviews: int = 200,
) -> List[Dict[str, Any]]:
    """Scan the dataset, select top products, and parse into the common schema."""
    download_snap_dataset()

    print("Pass 1: Scanning review counts per product...")
    product_counts = Counter()
    with gzip.open(LOCAL_GZ, "rt", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            asin = data.get("asin")
            if asin:
                product_counts[asin] += 1

    # Select top products meeting criteria
    candidate_products = set()
    total_selected = 0
    for asin, count in product_counts.most_common():
        if count < min_product_reviews:
            break
        candidate_products.add(asin)
        total_selected += count
        if len(candidate_products) >= top_n_products or total_selected >= target_reviews:
            break

    print(f"Selected {len(candidate_products)} products with {total_selected} candidate reviews.")

    print("Pass 2: Extracting, cleaning, and formatting reviews...")
    records = []
    prod_indices = Counter()

    with gzip.open(LOCAL_GZ, "rt", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            asin = data.get("asin")
            if asin not in candidate_products:
                continue

            raw_text = data.get("reviewText", "")
            if not raw_text or len(raw_text.strip()) < 10:
                continue

            prod_indices[asin] += 1
            idx = prod_indices[asin]
            review_id = f"amz_{asin}_{idx:05d}"

            # Rating: 1 to 5
            try:
                rating = int(round(float(data.get("overall", 3.0))))
                rating = max(1, min(5, rating))
            except (ValueError, TypeError):
                rating = 3

            # Date formatting (ISO 8601 YYYY-MM-DD)
            unix_ts = data.get("unixReviewTime")
            if unix_ts:
                try:
                    review_date = datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%d")
                except Exception:
                    review_date = "2014-01-01"
            else:
                review_date = "2014-01-01"

            cleaned_body = clean_text(raw_text)
            summary = clean_text(data.get("summary", ""))
            product_name = PRODUCT_NAMES.get(asin, f"Cell Phone Accessory {asin}")

            records.append({
                "review_id": review_id,
                "product_id": asin,
                "product_name": product_name,
                "category": "Cell Phones & Accessories",
                "text": cleaned_body,
                "summary": summary,
                "rating": rating,
                "date": review_date,
            })

            if len(records) >= target_reviews:
                break

    print(f"Parsed {len(records)} reviews across {len(candidate_products)} products.")

    PROCESSED_AMAZON_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_AMAZON_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"Saved processed Amazon reviews to: {PROCESSED_AMAZON_FILE}")
    return records


def load_amazon(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load processed Amazon reviews from disk."""
    if not PROCESSED_AMAZON_FILE.exists():
        parse_amazon_reviews()
    with open(PROCESSED_AMAZON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if limit:
        return data[:limit]
    return data


if __name__ == "__main__":
    parse_amazon_reviews(target_reviews=25000, top_n_products=70, min_product_reviews=200)
