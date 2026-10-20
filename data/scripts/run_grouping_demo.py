"""Run aspect extraction and grouping across demo products and print a cluster analysis table."""

import sys
from collections import Counter, defaultdict

from data.scripts.build_demo_sample import load_demo_sample
from nlp.aspects import extract_aspects
from nlp.grouping import get_aspect_grouper

# Ensure stdout handles UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_demo_grouping(max_reviews: int = 1500) -> None:
    """Run extraction and grouping on demo products and display results."""
    print("=" * 80)
    print(f" ASPECT GROUPING CLUSTER REPORT (Demo Products, sample up to {max_reviews:,} reviews)")
    print("=" * 80)

    reviews = load_demo_sample()[:max_reviews]
    grouper = get_aspect_grouper()

    print(f"Loaded {len(reviews):,} reviews across products. Extracting and grouping aspects...")

    canonical_mentions = Counter()
    canonical_variants = defaultdict(Counter)
    origin_counts = Counter()
    ungrouped_candidates = Counter()
    snippets_by_canonical = defaultdict(list)

    total_candidates = 0

    for r in reviews:
        text = r.get("text", "")
        if not text:
            continue

        cands = extract_aspects(text, method="spacy_chunks")
        for c in cands:
            total_candidates += 1
            canonical, origin, score = grouper.group_aspect(c.term)
            origin_counts[origin] += 1

            if origin != "unmatched":
                canonical_mentions[canonical] += 1
                canonical_variants[canonical][c.term.lower()] += 1
                if len(snippets_by_canonical[canonical]) < 3:
                    # Capture snippet
                    snippets_by_canonical[canonical].append(text[:120].replace("\n", " ") + "...")
            else:
                ungrouped_candidates[c.term.lower()] += 1

    print("\n" + "=" * 80)
    print(" 1. CANONICAL ASPECT CLUSTERS (Ranked by Mentions)")
    print("=" * 80)
    print(f" {'Canonical Aspect':<18} | {'Mentions':<9} | {'Top Member Variants / Terms'}")
    print(" " + "-" * 78)

    for canonical, count in canonical_mentions.most_common():
        variants = canonical_variants[canonical]
        top_vars = [f"{term} ({v_cnt})" for term, v_cnt in variants.most_common(6)]
        top_vars_str = ", ".join(top_vars)
        if len(variants) > 6:
            top_vars_str += f", +{len(variants) - 6} more"
        count_str = f"{count:,}"
        print(f" {canonical:<18} | {count_str:<9} | {top_vars_str}")

    print("\n" + "=" * 80)
    print(" 2. GROUPING METHOD ORIGIN DISTRIBUTION")
    print("=" * 80)
    for origin, count in origin_counts.most_common():
        pct = (count / total_candidates) * 100 if total_candidates > 0 else 0
        print(f" - {origin.capitalize():<12}: {count:,} candidates ({pct:.1f}%)")

    # 3. Emergent Clustering on Ungrouped Candidates
    print("\n" + "=" * 80)
    print(
        f" 3. UNGROUPED CANDIDATES ({len(ungrouped_candidates)} distinct terms, {sum(ungrouped_candidates.values()):,} total mentions)"
    )
    print("=" * 80)

    top_ungrouped = ungrouped_candidates.most_common(25)
    print(" Top 25 ungrouped candidate terms:")
    for term, count in top_ungrouped:
        print(f"   * {term:<24} ({count} mentions)")

    # Run AgglomerativeClustering on top ungrouped terms
    frequent_ungrouped = [term for term, cnt in ungrouped_candidates.items() if cnt >= 3]
    if frequent_ungrouped:
        print(
            f"\n Discovered Emergent Clusters from ungrouped terms (>= 3 mentions, {len(frequent_ungrouped)} terms):"
        )
        clusters = grouper.cluster_unmatched(frequent_ungrouped, distance_threshold=0.40)
        for c_name, members in sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True):
            if len(members) > 1:
                print(f"   Cluster '{c_name}': {', '.join(members[:8])}")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    run_demo_grouping(max_reviews=1500)
