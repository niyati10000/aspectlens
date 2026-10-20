"""Download and parse SemEval-2014 Task 4 datasets (laptops and restaurants)."""

import os
import ssl
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional

from nlp.preprocess import clean_text

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_SEMEVAL_DIR = BASE_DIR / "data" / "raw" / "semeval"
PROCESSED_SEMEVAL_FILE = BASE_DIR / "data" / "processed_semeval.json"

URLS = {
    "laptop_train": "https://raw.githubusercontent.com/fani-lab/LADy/main/data/raw/semeval/SemEval-14/Laptop_Train_v2.xml",
    "laptop_test": "https://raw.githubusercontent.com/shenwzh3/RGAT-ABSA/master/data/semeval14/Laptops_Test_Gold.xml",
    "restaurant_train": "https://raw.githubusercontent.com/fani-lab/LADy/main/data/raw/semeval/SemEval-14/Restaurants_Train_v2.xml",
    "restaurant_test": "https://raw.githubusercontent.com/shenwzh3/RGAT-ABSA/master/data/semeval14/Restaurants_Test_Gold.xml",
}


def download_file(url: str, dest_path: Path) -> None:
    """Download a remote URL to dest_path with SSL bypass if needed."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"File already exists: {dest_path}")
        return

    print(f"Downloading {url} -> {dest_path}...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp, open(dest_path, "wb") as f:
        f.write(resp.read())
    print(f"Saved: {dest_path} ({dest_path.stat().st_size} bytes)")


def parse_semeval_xml(xml_path: Path, domain: str, split: str) -> List[Dict[str, Any]]:
    """Parse SemEval-2014 Task 4 XML file into common schema + evaluation aspect terms."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    records = []

    for sentence in root.findall("sentence"):
        s_id = sentence.get("id")
        text_elem = sentence.find("text")
        if text_elem is None or not text_elem.text:
            continue
        raw_text = text_elem.text

        aspect_terms = []
        aspect_terms_elem = sentence.find("aspectTerms")
        if aspect_terms_elem is not None:
            for a_term in aspect_terms_elem.findall("aspectTerm"):
                term = a_term.get("term")
                polarity = a_term.get("polarity")
                from_idx = int(a_term.get("from", -1))
                to_idx = int(a_term.get("to", -1))
                if term and polarity:
                    aspect_terms.append({
                        "term": term,
                        "polarity": polarity,
                        "from": from_idx,
                        "to": to_idx,
                    })

        aspect_categories = []
        aspect_cats_elem = sentence.find("aspectCategories")
        if aspect_cats_elem is not None:
            for a_cat in aspect_cats_elem.findall("aspectCategory"):
                cat = a_cat.get("category")
                polarity = a_cat.get("polarity")
                if cat and polarity:
                    aspect_categories.append({
                        "category": cat,
                        "polarity": polarity,
                    })

        # Common schema mapping
        records.append({
            "review_id": f"semeval_{domain}_{split}_{s_id}",
            "product_id": f"semeval_{domain}",
            "text": clean_text(raw_text),
            "raw_text": raw_text,
            "rating": None,
            "date": "2014-01-01",
            "domain": domain,
            "split": split,
            "aspect_terms": aspect_terms,
            "aspect_categories": aspect_categories,
        })

    return records


def process_semeval() -> List[Dict[str, Any]]:
    """Download and process all SemEval splits."""
    all_records = []
    RAW_SEMEVAL_DIR.mkdir(parents=True, exist_ok=True)

    for key, url in URLS.items():
        domain, split = key.split("_")
        dest = RAW_SEMEVAL_DIR / f"{domain}_{split}.xml"
        download_file(url, dest)
        split_records = parse_semeval_xml(dest, domain=domain, split=split)
        print(f"Parsed {len(split_records)} sentences for {domain} ({split})")
        all_records.extend(split_records)

    with open(PROCESSED_SEMEVAL_FILE, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)

    print(f"Total SemEval records processed: {len(all_records)}")
    print(f"Saved to: {PROCESSED_SEMEVAL_FILE}")
    return all_records


def load_semeval(split: Optional[str] = None, domain: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load processed SemEval dataset with optional filtering."""
    if not PROCESSED_SEMEVAL_FILE.exists():
        process_semeval()
    with open(PROCESSED_SEMEVAL_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)
    if split:
        records = [r for r in records if r.get("split") == split]
    if domain:
        records = [r for r in records if r.get("domain") == domain]
    return records


if __name__ == "__main__":
    process_semeval()
