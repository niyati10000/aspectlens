"""Aspect sentiment classification benchmark on SemEval-2014 Task 4 test split.

Evaluates aspect sentiment accuracy and macro-F1 across:
1. VADER Scorer (rule-based with domain lexicon and intensifier handling)
2. Transformer Scorer (cardiffnlp/twitter-roberta-base-sentiment-latest)
3. FineTuned Scorer (stub with fallback for paired ABSA cross-encoder)

Evaluates on identical test splits and saves results to:
- eval/results/sentiment_benchmark.json
- eval/results/sentiment_benchmark.csv
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
)

from nlp.aspects import get_spacy_model
from nlp.opinions import extract_opinions_for_aspect, split_into_clauses
from nlp.sentiment import FineTunedScorer, Scorer, TransformerScorer, VADERScorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "processed_semeval.json"
RESULTS_DIR = BASE_DIR / "eval" / "results"

VALID_POLARITIES = {"positive", "negative", "neutral"}


def evaluate_scorer_on_instances(
    scorer: Scorer,
    instances: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate a sentiment scorer on a list of prepared test aspect instances."""
    golds: list[str] = []
    preds: list[str] = []
    clause_cache: dict[str, Any] = {}

    for inst in instances:
        clause = inst["clause"]
        aspect = inst["aspect"]
        opinion_words = inst["opinion_words"]
        gold_polarity = inst["gold_polarity"]

        # Cache transformer outputs per unique (clause, aspect) for efficiency
        cache_key = f"{clause}||{aspect}"
        if cache_key in clause_cache:
            res = clause_cache[cache_key]
        else:
            res = scorer.score(clause, aspect, opinion_words)
            clause_cache[cache_key] = res

        golds.append(gold_polarity)
        preds.append(res.label)

    acc = float(accuracy_score(golds, preds))
    macro_f1 = float(f1_score(golds, preds, average="macro", zero_division=0))

    # Per-class metrics
    labels = ["positive", "neutral", "negative"]
    p_arr, r_arr, f_arr, s_arr = precision_recall_fscore_support(
        golds, preds, labels=labels, zero_division=0
    )

    per_class = {}
    for idx, label in enumerate(labels):
        per_class[label] = {
            "precision": round(float(p_arr[idx]), 4),
            "recall": round(float(r_arr[idx]), 4),
            "f1": round(float(f_arr[idx]), 4),
            "support": int(s_arr[idx]),
        }

    return {
        "scorer": scorer.name,
        "accuracy": round(acc, 4),
        "macro_f1": round(macro_f1, 4),
        "total_instances": len(golds),
        "per_class": per_class,
    }


def run_sentiment_evaluation(
    data_path: Path = DATA_PATH,
    results_dir: Path = RESULTS_DIR,
    sample_limit: int = 0,
) -> dict[str, Any]:
    """Run aspect sentiment evaluation across VADER, Transformer, and FineTuned models on identical splits."""
    logger.info("Loading SemEval data from %s", data_path)
    with open(data_path, encoding="utf-8") as f:
        all_data = json.load(f)

    test_docs = [row for row in all_data if row.get("split") == "test"]
    if sample_limit > 0:
        test_docs = test_docs[:sample_limit]

    logger.info("Extracting aspect instances from %d test sentences...", len(test_docs))

    nlp = get_spacy_model()
    instances: list[dict[str, Any]] = []

    for row in test_docs:
        aspects = row.get("aspect_terms", [])
        if not aspects:
            continue

        text = row["text"]
        doc = nlp(text)
        clauses = split_into_clauses(doc)

        for a in aspects:
            pol = a.get("polarity", "").strip().lower()
            if pol not in VALID_POLARITIES:
                # Exclude conflict labels per standard 3-class ABSA benchmark methodology
                continue

            term = a["term"]
            start = a["from"]
            end = a["to"]

            opinion_words, clause_text = extract_opinions_for_aspect(doc, start, end, clauses)

            instances.append(
                {
                    "sentence": text,
                    "aspect": term,
                    "gold_polarity": pol,
                    "start": start,
                    "end": end,
                    "clause": clause_text,
                    "opinion_words": opinion_words,
                }
            )

    logger.info(
        "Prepared %d test aspect instances across %d sentences.", len(instances), len(test_docs)
    )

    # Instantiate scorers
    logger.info("Evaluating VADER Scorer...")
    vader = VADERScorer()
    vader_res = evaluate_scorer_on_instances(vader, instances)

    logger.info("Evaluating Transformer Scorer (RoBERTa)...")
    transformer = TransformerScorer()
    transformer_res = evaluate_scorer_on_instances(transformer, instances)

    logger.info("Evaluating FineTuned Scorer (Stub)...")
    finetuned = FineTunedScorer()
    finetuned_res = evaluate_scorer_on_instances(finetuned, instances)

    results_list = [vader_res, transformer_res, finetuned_res]

    output_payload = {
        "benchmark": "aspect_sentiment_benchmark",
        "dataset": "SemEval-2014 Task 4 Test Split",
        "total_aspect_instances": len(instances),
        "results": results_list,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "sentiment_benchmark.json"
    csv_path = results_dir / "sentiment_benchmark.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    logger.info("Saved JSON results to %s", json_path)

    # Flatten for CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "scorer",
            "accuracy",
            "macro_f1",
            "total_instances",
            "pos_f1",
            "neu_f1",
            "neg_f1",
            "pos_precision",
            "pos_recall",
            "neg_precision",
            "neg_recall",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results_list:
            writer.writerow(
                {
                    "scorer": r["scorer"],
                    "accuracy": r["accuracy"],
                    "macro_f1": r["macro_f1"],
                    "total_instances": r["total_instances"],
                    "pos_f1": r["per_class"]["positive"]["f1"],
                    "neu_f1": r["per_class"]["neutral"]["f1"],
                    "neg_f1": r["per_class"]["negative"]["f1"],
                    "pos_precision": r["per_class"]["positive"]["precision"],
                    "pos_recall": r["per_class"]["positive"]["recall"],
                    "neg_precision": r["per_class"]["negative"]["precision"],
                    "neg_recall": r["per_class"]["negative"]["recall"],
                }
            )
    logger.info("Saved CSV results to %s", csv_path)

    return output_payload


if __name__ == "__main__":
    results = run_sentiment_evaluation()
    print("\n=== SemEval-2014 Aspect Sentiment Classification Results ===")
    for r in results["results"]:
        print(
            f"[{r['scorer'].upper()}] Accuracy: {r['accuracy']:.4f} | Macro-F1: {r['macro_f1']:.4f}"
        )
