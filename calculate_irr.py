#!/usr/bin/env python3
"""
Calculate Inter-Rater Reliability (IRR) metrics for double-coded annotations.

Computes:
- Cohen's Kappa (binary agreement)
- Krippendorff's Alpha (more robust)
- Percent agreement
- Confusion matrices
"""

import sqlite3
import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix
import pandas as pd
from datetime import datetime

DB_PATH = "data/youtube_comments.db"


def _format_metric(value):
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.3f}"


def _to_json_float(value):
    if value is None or pd.isna(value):
        return None
    return float(value)


def krippendorff_alpha(data, level_of_measurement='nominal'):
    """
    Calculate Krippendorff's Alpha for inter-rater reliability.

    Args:
        data: numpy array of shape (n_items, n_raters)
        level_of_measurement: 'nominal', 'ordinal', 'interval', or 'ratio'

    Returns:
        alpha: Krippendorff's alpha coefficient
    """
    # Convert to float, treating NaN as missing
    data = np.array(data, dtype=float)
    n_items, n_raters = data.shape

    # Calculate observed disagreement
    def delta(v1, v2):
        """Difference function for nominal data"""
        if level_of_measurement == 'nominal':
            return 0 if v1 == v2 else 1
        else:  # ordinal, interval, ratio
            return (v1 - v2) ** 2

    # Pairable values
    pairable = []
    for i in range(n_items):
        item_values = data[i, ~np.isnan(data[i, :])]
        if len(item_values) >= 2:
            for j in range(len(item_values)):
                for k in range(j + 1, len(item_values)):
                    pairable.append((item_values[j], item_values[k]))

    if len(pairable) == 0:
        return np.nan

    # Observed disagreement
    D_o = sum(delta(v1, v2) for v1, v2 in pairable) / len(pairable)

    # Expected disagreement
    all_values = data[~np.isnan(data)]
    if len(all_values) == 0:
        return np.nan

    unique_values = np.unique(all_values)
    n_total = len(all_values)

    D_e = 0
    for v1 in unique_values:
        for v2 in unique_values:
            n_v1 = np.sum(all_values == v1)
            n_v2 = np.sum(all_values == v2)
            D_e += (n_v1 * n_v2 * delta(v1, v2)) / (n_total * (n_total - 1))

    if D_e == 0:
        return 1.0 if D_o == 0 else 0.0

    alpha = 1 - (D_o / D_e)
    return alpha


def get_double_coded_data(conn):
    """Fetch all double-coded annotations (original coder labels before adjudication)"""

    # Get all comments with exactly 2 coders
    # For each, get the 2 non-adjudicated annotations (the original coder labels)
    query = """
    WITH double_coded_comments AS (
        SELECT comment_db_id
        FROM annotations
        GROUP BY comment_db_id
        HAVING COUNT(DISTINCT annotator_id) >= 2
    )
    SELECT
        a1.comment_db_id,
        a1.annotator_id as annotator_1,
        a1.skepticism_fake_callout as skepticism_1,
        a1.proof_demand as proof_1,
        a1.normalization_defense as normalization_1,
        a2.annotator_id as annotator_2,
        a2.skepticism_fake_callout as skepticism_2,
        a2.proof_demand as proof_2,
        a2.normalization_defense as normalization_2
    FROM annotations a1
    JOIN annotations a2 ON a1.comment_db_id = a2.comment_db_id
    WHERE a1.comment_db_id IN (SELECT comment_db_id FROM double_coded_comments)
      AND a1.annotator_id != a2.annotator_id
      AND a1.annotator_id < a2.annotator_id
      AND a1.is_adjudicated = 0
      AND a2.is_adjudicated = 0
    ORDER BY a1.comment_db_id;
    """

    df = pd.read_sql_query(query, conn)
    return df


def get_disagreement_status(conn):
    """Fetch disagreement and adjudication status across double-coded comments."""
    query = """
    WITH per_comment AS (
        SELECT
            a.comment_db_id,
            COUNT(DISTINCT a.annotator_id) AS coder_count,
            MAX(a.is_adjudicated) AS has_adjudicated,
            MIN(COALESCE(a.skepticism_fake_callout, 0)) AS min_s,
            MAX(COALESCE(a.skepticism_fake_callout, 0)) AS max_s,
            MIN(COALESCE(a.proof_demand, 0)) AS min_p,
            MAX(COALESCE(a.proof_demand, 0)) AS max_p,
            MIN(COALESCE(a.normalization_defense, 0)) AS min_n,
            MAX(COALESCE(a.normalization_defense, 0)) AS max_n
        FROM annotations a
        GROUP BY a.comment_db_id
    )
    SELECT
        SUM(CASE WHEN coder_count >= 2 THEN 1 ELSE 0 END) AS total_double_coded,
        SUM(CASE WHEN coder_count >= 2 AND has_adjudicated = 1 THEN 1 ELSE 0 END) AS adjudicated_comments,
        SUM(
            CASE
                WHEN coder_count >= 2 AND (min_s <> max_s OR min_p <> max_p OR min_n <> max_n) THEN 1
                ELSE 0
            END
        ) AS disagreement_comments,
        SUM(
            CASE
                WHEN coder_count >= 2
                     AND has_adjudicated = 0
                     AND (min_s <> max_s OR min_p <> max_p OR min_n <> max_n) THEN 1
                ELSE 0
            END
        ) AS unresolved_disagreements
    FROM per_comment
    """
    row = conn.execute(query).fetchone()
    return {
        "total_double_coded": int(row[0] or 0),
        "adjudicated_comments": int(row[1] or 0),
        "disagreement_comments": int(row[2] or 0),
        "unresolved_disagreements": int(row[3] or 0),
    }


def calculate_agreement_stats(labels_1, labels_2, label_name):
    """Calculate agreement statistics for a single label"""

    # Perfect agreement percentage
    agreement = np.mean(labels_1 == labels_2)

    # Cohen's Kappa
    kappa = cohen_kappa_score(labels_1, labels_2)

    # Confusion matrix
    cm = confusion_matrix(labels_1, labels_2, labels=[0, 1])

    # Krippendorff's Alpha (reshape to n_items × n_raters format)
    data_for_alpha = np.column_stack([labels_1, labels_2])
    alpha = krippendorff_alpha(data_for_alpha, level_of_measurement='nominal')

    return {
        'label': label_name,
        'n_pairs': len(labels_1),
        'agreement': agreement,
        'cohen_kappa': kappa,
        'krippendorff_alpha': alpha,
        'confusion_matrix': cm
    }


def main():
    """Calculate and report IRR metrics"""

    print("=" * 60)
    print("INTER-RATER RELIABILITY (IRR) ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Connect to database
    conn = sqlite3.connect(DB_PATH)

    # Fetch double-coded data
    print("Fetching double-coded annotations...")
    df = get_double_coded_data(conn)
    print(f"✓ Found {len(df):,} double-coded comment pairs\n")
    if df.empty:
        print("❌ No non-adjudicated double-coded pairs available for IRR.")
        conn.close()
        return

    # Calculate IRR for each label
    results = []

    for label in ['skepticism', 'proof', 'normalization']:
        col_1 = f"{label}_1"
        col_2 = f"{label}_2"

        stats = calculate_agreement_stats(
            df[col_1].values,
            df[col_2].values,
            label
        )
        results.append(stats)

    # Print summary table
    print("=" * 60)
    print("SUMMARY: Inter-Rater Reliability Metrics")
    print("=" * 60)
    print()
    print(f"{'Label':<20} {'N Pairs':<10} {'Agreement':<12} {'Kappa':<10} {'Alpha':<10}")
    print("-" * 60)

    for r in results:
        print(f"{r['label'].capitalize():<20} {r['n_pairs']:<10} "
              f"{r['agreement']:.3f} ({r['agreement']*100:.1f}%)  "
              f"{_format_metric(r['cohen_kappa']):<10} {_format_metric(r['krippendorff_alpha'])}")

    print()
    print("=" * 60)
    print("INTERPRETATION GUIDELINES")
    print("=" * 60)
    print()
    print("Cohen's Kappa / Krippendorff's Alpha:")
    print("  < 0.00  = Poor agreement (less than chance)")
    print("  0.00-0.20 = Slight agreement")
    print("  0.21-0.40 = Fair agreement")
    print("  0.41-0.60 = Moderate agreement")
    print("  0.61-0.80 = Substantial agreement")
    print("  0.81-1.00 = Almost perfect agreement")
    print()

    # Detailed confusion matrices
    print("=" * 60)
    print("CONFUSION MATRICES (Rows=Annotator 1, Cols=Annotator 2)")
    print("=" * 60)
    print()

    for r in results:
        print(f"\n{r['label'].upper()}:")
        cm = r['confusion_matrix']
        print(f"             Annotator 2")
        print(f"             0 (neg)   1 (pos)")
        print(f"Annotator 1")
        print(f"  0 (neg)    {cm[0,0]:<8}  {cm[0,1]:<8}  = {cm[0,0] + cm[0,1]} total")
        print(f"  1 (pos)    {cm[1,0]:<8}  {cm[1,1]:<8}  = {cm[1,0] + cm[1,1]} total")
        print(f"             {cm[0,0] + cm[1,0]} total   {cm[0,1] + cm[1,1]} total")

        # Calculate disagreement breakdown
        total = cm.sum()
        agree_both_0 = cm[0, 0]
        agree_both_1 = cm[1, 1]
        disagree = cm[0, 1] + cm[1, 0]

        print(f"\n  Agreement on 0 (both negative): {agree_both_0} ({agree_both_0/total*100:.1f}%)")
        print(f"  Agreement on 1 (both positive): {agree_both_1} ({agree_both_1/total*100:.1f}%)")
        print(f"  Disagreements: {disagree} ({disagree/total*100:.1f}%)")

    print()
    print("=" * 60)
    print("DISAGREEMENT RESOLUTION")
    print("=" * 60)
    print()

    status = get_disagreement_status(conn)
    total_double = status["total_double_coded"]
    adjudicated = status["adjudicated_comments"]
    disagreement_comments = status["disagreement_comments"]
    unresolved_disagreements = status["unresolved_disagreements"]
    non_adjudicated = max(0, total_double - adjudicated)

    print(f"Total double-coded comments: {total_double:,}")
    print(f"Comments with adjudication: {adjudicated:,}")
    print(f"Non-adjudicated comments: {non_adjudicated:,}")
    print(f"Disagreement comments (core labels): {disagreement_comments:,}")
    print(f"Unresolved disagreements (core labels): {unresolved_disagreements:,}")
    print()

    # Calculate overall disagreement rate
    total_disagreements = sum(r['n_pairs'] * (1 - r['agreement']) for r in results)
    total_judgments = sum(r['n_pairs'] for r in results)
    overall_agreement = 1 - (total_disagreements / total_judgments)

    print(f"Overall agreement rate (across all 3 labels): {overall_agreement:.3f} ({overall_agreement*100:.1f}%)")
    print(f"Overall disagreement rate: {1-overall_agreement:.3f} ({(1-overall_agreement)*100:.1f}%)")
    print()

    conn.close()

    # Save results to JSON
    import json

    output = {
        'generated_at': datetime.now().isoformat(),
        'n_double_coded_pairs': len(df),
        'metrics': [
            {
                'label': r['label'],
                'n_pairs': int(r['n_pairs']),
                'percent_agreement': float(r['agreement']),
                'cohen_kappa': _to_json_float(r['cohen_kappa']),
                'krippendorff_alpha': _to_json_float(r['krippendorff_alpha']),
                'confusion_matrix': r['confusion_matrix'].tolist()
            }
            for r in results
        ],
        'overall_agreement': float(overall_agreement),
        'overall_disagreement': float(1 - overall_agreement),
        'adjudication_status': {
            'total_double_coded': int(total_double),
            'adjudicated_comments': int(adjudicated),
            'non_adjudicated_comments': int(non_adjudicated),
            'disagreement_comments_core_labels': int(disagreement_comments),
            'unresolved_disagreements_core_labels': int(unresolved_disagreements),
        }
    }

    output_path = "data/irr_metrics_2026-04-03.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Results saved to: {output_path}")
    print()


if __name__ == '__main__':
    main()
