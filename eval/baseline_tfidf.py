"""TF-IDF + Logistic Regression whole-review baseline benchmark.

Trains a traditional TF-IDF + Logistic Regression model on SemEval-2014 training sentences
and evaluates its performance on test aspect instances. Because whole-review models predict
a single label for the entire text, they cannot resolve multi-aspect clauses or contrastive
sentiments (e.g. 'Screen is great but battery is bad').

Saves comparison to:
- eval/results/baseline_comparison.json
- eval/results/baseline_comparison.csv
"""

import json
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "processed_semeval.json"
RESULTS_DIR = BASE_DIR / "eval" / "results"

VALID_POLARITIES = {"positive", "negative", "neutral"}


def run_baseline_evaluation(
    data_path: Path = DATA_PATH,
    results_dir: Path = RESULTS_DIR,
    sample_limit: int = 0,
) -> Dict[str, Any]:
    """Train whole-review TF-IDF baseline and evaluate against aspect-level test ground truth."""
    logger.info("Loading SemEval data from %s", data_path)
    with open(data_path, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    train_docs = [r for r in all_data if r.get("split") == "train"]
    test_docs = [r for r in all_data if r.get("split") == "test"]

    if sample_limit > 0:
        test_docs = test_docs[:sample_limit]

    logger.info("Preparing training set from %d SemEval train sentences...", len(train_docs))
    train_texts: List[str] = []
    train_labels: List[str] = []

    for row in train_docs:
        aspects = row.get("aspect_terms", [])
        for a in aspects:
            pol = a.get("polarity", "").strip().lower()
            if pol in VALID_POLARITIES:
                train_texts.append(row["text"])
                train_labels.append(pol)

    logger.info("Training samples: %d", len(train_texts))

    # Vectorize and train Logistic Regression with fixed random seed
    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    X_train = vectorizer.fit_transform(train_texts)

    clf = LogisticRegression(
        random_state=42,
        max_iter=1000,
        class_weight="balanced",
    )
    clf.fit(X_train, train_labels)
    logger.info("Fitted Logistic Regression baseline (classes=%s)", list(clf.classes_))

    # Evaluate on test aspect instances
    logger.info("Evaluating whole-review baseline on test split...")
    test_golds: List[str] = []
    test_preds: List[str] = []

    # Cache predictions per test text
    text_pred_cache: Dict[str, str] = {}

    for row in test_docs:
        aspects = row.get("aspect_terms", [])
        if not aspects:
            continue

        text = row["text"]
        if text in text_pred_cache:
            sentence_pred = text_pred_cache[text]
        else:
            feat = vectorizer.transform([text])
            sentence_pred = str(clf.predict(feat)[0])
            text_pred_cache[text] = sentence_pred

        for a in aspects:
            pol = a.get("polarity", "").strip().lower()
            if pol in VALID_POLARITIES:
                test_golds.append(pol)
                # Whole-review model assigns sentence-level prediction to every aspect
                test_preds.append(sentence_pred)

    acc = float(accuracy_score(test_golds, test_preds))
    macro_f1 = float(f1_score(test_golds, test_preds, average="macro", zero_division=0))

    labels = ["positive", "neutral", "negative"]
    p_arr, r_arr, f_arr, s_arr = precision_recall_fscore_support(
        test_golds, test_preds, labels=labels, zero_division=0
    )

    per_class = {}
    for idx, label in enumerate(labels):
        per_class[label] = {
            "precision": round(float(p_arr[idx]), 4),
            "recall": round(float(r_arr[idx]), 4),
            "f1": round(float(f_arr[idx]), 4),
            "support": int(s_arr[idx]),
        }

    baseline_metrics = {
        "model": "tfidf_logistic_regression_whole_review",
        "description": "TF-IDF (1-2 grams) + Logistic Regression applied to entire sentence",
        "accuracy": round(acc, 4),
        "macro_f1": round(macro_f1, 4),
        "total_instances": len(test_golds),
        "per_class": per_class,
    }

    # Load sentiment_benchmark.json if available to include comparison
    sentiment_path = results_dir / "sentiment_benchmark.json"
    comparison_entries = [baseline_metrics]
    if sentiment_path.exists():
        try:
            with open(sentiment_path, "r", encoding="utf-8") as f:
                sb_data = json.load(f)
                for item in sb_data.get("results", []):
                    comparison_entries.append({
                        "model": item["scorer"],
                        "description": f"AspectLens clause-scoped {item['scorer']} scorer",
                        "accuracy": item["accuracy"],
                        "macro_f1": item["macro_f1"],
                        "total_instances": item["total_instances"],
                        "per_class": item["per_class"],
                    })
        except Exception as e:
            logger.warning("Could not read sentiment_benchmark for comparison: %s", e)

    output_payload = {
        "benchmark": "baseline_comparison",
        "dataset": "SemEval-2014 Task 4 Test Split",
        "baseline": baseline_metrics,
        "comparison": comparison_entries,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "baseline_comparison.json"
    csv_path = results_dir / "baseline_comparison.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    logger.info("Saved JSON results to %s", json_path)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["model", "accuracy", "macro_f1", "pos_f1", "neu_f1", "neg_f1"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in comparison_entries:
            writer.writerow({
                "model": c["model"],
                "accuracy": c["accuracy"],
                "macro_f1": c["macro_f1"],
                "pos_f1": c["per_class"]["positive"]["f1"],
                "neu_f1": c["per_class"]["neutral"]["f1"],
                "neg_f1": c["per_class"]["negative"]["f1"],
            })
    logger.info("Saved CSV results to %s", csv_path)

    return output_payload


if __name__ == "__main__":
    results = run_baseline_evaluation()
    b = results["baseline"]
    print(f"\n=== Baseline TF-IDF + Logistic Regression Results ===")
    print(f"Accuracy: {b['accuracy']:.4f} | Macro-F1: {b['macro_f1']:.4f}")
