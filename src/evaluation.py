"""Evaluation helpers shared by the forecasting and exposure notebooks."""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

from src.geo import SECTOR_DEG, angle_diff_deg


def threshold_for_recall(y_true, score, target_recall):
    """Highest score threshold whose recall (score >= threshold) is at least target_recall."""
    pos_scores = np.sort(np.asarray(score, dtype=float)[np.asarray(y_true) == 1])[::-1]
    k = int(np.ceil(target_recall * len(pos_scores)))
    return pos_scores[k - 1]


def binary_summary(y_true, flagged, score):
    """Recall, precision, F1, PR-AUC and counts for a set of flags and a ranking score."""
    return {
        "recall": recall_score(y_true, flagged, zero_division=0),
        "precision": precision_score(y_true, flagged, zero_division=0),
        "f1": f1_score(y_true, flagged, zero_division=0),
        "pr_auc": average_precision_score(y_true, score),
        "n_flagged": int(np.sum(flagged)),
        "n_positive": int(np.sum(y_true)),
        "n_rows": int(len(y_true)),
    }


def sector_gap(sector_a, sector_b):
    """Number of 8-point sectors between two sector labels (0 to 4)."""
    deg_a = pd.Series(sector_a).map(SECTOR_DEG).to_numpy(dtype=float)
    deg_b = pd.Series(sector_b).map(SECTOR_DEG).to_numpy(dtype=float)
    return angle_diff_deg(deg_a, deg_b) / 45


def flag_closest_per_group(dist, group, n_per_group):
    """Flag the n closest rows in each group; n_per_group maps group to n."""
    df = pd.DataFrame({"dist": np.asarray(dist), "group": np.asarray(group)})
    rank = df.groupby("group")["dist"].rank(method="first")
    return (rank <= df["group"].map(n_per_group).fillna(0)).to_numpy().astype(int)
