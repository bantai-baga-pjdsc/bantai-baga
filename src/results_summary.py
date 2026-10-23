"""2026 test results against our original targets, and the limitations list, shared by the dashboard and the README."""
import pandas as pd

# targets set before the 2026 test
DRIFT_TARGET = 0.60
RECALL_TARGET = 0.75
FINAL_MODEL_LABEL = "Final model (chosen by 2024-2025 cross-validation)"
COMPARISON_MODEL = {"LightGBM": "MLP", "MLP": "LightGBM"}


def exact_share(rate, n):
    """Share recovered from its count; metrics.json rounds rates to 4 decimals, which can shift the 1-decimal %."""
    return round(rate * n) / n


def both_status(final_met, comparison_met):
    """Status of one target for the final and the comparison model."""
    if final_met == comparison_met:
        return "Met by both" if final_met else "Missed by both"
    return "Met by final model only" if final_met else "Met by comparison model only"


def model_results_table(metrics):
    """2026 test results of the final and the comparison model per task, against our original targets."""
    pct = "{:.1%}".format
    so2, drift, exposure = (metrics[k] for k in ["so2_next_day", "drift_next_day", "exposure"])
    so2_final, drift_final, exp_final = so2["forecast_model"], drift["forecast_model"], exposure["scoring_model"]
    so2_comp, drift_comp, exp_comp = (COMPARISON_MODEL[m] for m in (so2_final, drift_final, exp_final))
    mae = {k: v["mae_td"] for k, v in so2["test"].items()}
    accuracy = {k: exact_share(v["accuracy"], v["n_eval"]) for k, v in drift["test"].items()}
    recall = {k: exact_share(v["recall"], v["n_positive"]) for k, v in exposure["test"].items()}
    pr_auc = {k: v["pr_auc"] for k, v in exposure["test"].items()}
    distance = {m: f"distance only (N from {m})" for m in (exp_final, exp_comp)}
    best_drift_baseline = max(accuracy["repeat yesterday"], accuracy["always SW"])
    drift_baselines = (f"Repeat yesterday {pct(accuracy['repeat yesterday'])}, "
                       f"always SW {pct(accuracy['always SW'])}")
    rows = [
        ("Next-day SO2 emission", "No target", f"{so2_final} MAE {mae[so2_final]:,.0f} t/d",
         f"{so2_comp} MAE {mae[so2_comp]:,.0f} t/d",
         f"Persistence {mae['persistence']:,.0f} t/d, 7-day mean {mae['7-day mean']:,.0f} t/d", "No target"),
        ("Next-day drift direction", f"Correct on at least {DRIFT_TARGET:.0%} of 2026 days",
         f"{drift_final} {pct(accuracy[drift_final])}", f"{drift_comp} {pct(accuracy[drift_comp])}",
         drift_baselines, both_status(accuracy[drift_final] >= DRIFT_TARGET, accuracy[drift_comp] >= DRIFT_TARGET)),
        ("Next-day drift direction", "Beat both baselines", f"{drift_final} {pct(accuracy[drift_final])}",
         f"{drift_comp} {pct(accuracy[drift_comp])}", drift_baselines,
         both_status(accuracy[drift_final] > best_drift_baseline, accuracy[drift_comp] > best_drift_baseline)),
        ("Exposure (where)", f"Catch at least {RECALL_TARGET:.0%} of reported exposures (recall)",
         f"{exp_final} {pct(recall[exp_final])}", f"{exp_comp} {pct(recall[exp_comp])}", "See next row",
         both_status(recall[exp_final] >= RECALL_TARGET, recall[exp_comp] >= RECALL_TARGET)),
        ("Exposure (where)", "Beat distance only, flagging the same number of barangays",
         f"{exp_final} recall {pct(recall[exp_final])}, PR-AUC {pr_auc[exp_final]:.2f}",
         f"{exp_comp} recall {pct(recall[exp_comp])}, PR-AUC {pr_auc[exp_comp]:.2f}",
         f"Distance only: recall {pct(recall[distance[exp_final]])} (as many flagged as {exp_final}), "
         f"{pct(recall[distance[exp_comp]])} (as many as {exp_comp}); PR-AUC {pr_auc[distance[exp_final]]:.2f}",
         both_status(recall[exp_final] > recall[distance[exp_final]],
                     recall[exp_comp] > recall[distance[exp_comp]])),
    ]
    return pd.DataFrame(rows, columns=["Task", "Target", FINAL_MODEL_LABEL, "Comparison model", "Baselines",
                                       "Status"])


def plan_results_table(metrics):
    """2026 report-day results of the model plan and the distance-only plan."""
    plan = metrics["allocation"]
    covered = {k: plan[f"vulnerable_covered_{k}"] for k in ["model", "distance"]}
    share = {k: covered[k] / plan["reported_vulnerable"] for k in covered}
    kits_total = plan["report_days"] * plan["scenario_kits"]
    rows = [
        ("Team coverage", "Cover more under-5 and 60+ residents of reported barangays than a distance-only plan",
         f"{share['model']:.1%} ({covered['model']:,} of {plan['reported_vulnerable']:,})",
         f"{share['distance']:.1%} ({covered['distance']:,})",
         "Met" if covered["model"] > covered["distance"] else "Missed"),
        ("Nebulizer kits at bases serving a reported barangay", "No target",
         f"{plan['kits_serving_reported_model']:,} of {kits_total:,}",
         f"{plan['kits_serving_reported_distance']:,} of {kits_total:,}", "No target"),
        ("Masks to reported barangays", "No target", f"{plan['masks_to_reported_model']:,}",
         f"{plan['masks_to_reported_distance']:,}", "No target"),
    ]
    return pd.DataFrame(rows, columns=["Measure", "Target", "Model plan", "Distance-only plan", "Status"])


def limitations(metrics):
    """Limitations of the data, models and response plan, one plain sentence or two each."""
    exposure = metrics["exposure"]
    return [
        f"Few events: the exposure model learned from {len(exposure['train_event_dates'])} event days in "
        f"2024-2025 and was tested on {len(exposure['test_event_dates'])} in 2026.",
        "The report log undercounts exposure: many news reports give only the number of affected barangays, and "
        "quiet days are rarely reported.",
        "The model predicts where exposure happens on an event day, not when events happen. Ashfall from sudden "
        "eruptions does not follow daily SO2.",
        "The exposure model was trained on report days only, so it ranks barangays even on quiet days; the daily "
        "outlook scales risk by forecast SO2 for this reason.",
        "SO2 levels are scenarios. We have emission at the crater (t/d), not concentrations where people live, "
        f"so the SO2 rise assumes {metrics['health_impact']['main_scenario_ugm3']} µg/m³ for a barangay that is "
        "surely exposed on a typical report day.",
        "The FHSIS 2022 baseline is likely low, since it counts only cases reported through public health "
        "facilities.",
        "FHSIS 2022 has no rate for adults 60 and over, so we use the all-ages rate.",
        "Bacolod City uses its own FHSIS rate; Negros Oriental uses the Negros Occidental rate because its own "
        "figures look underreported.",
        "Health facilities come from OpenStreetMap, which may miss some barangay health stations.",
        "Past wind comes from Open-Meteo's historical record, which is a model analysis, not wind measured at "
        "the crater. The live forecast uses Open-Meteo's forecast, which adds forecast error.",
        "The live forecast holds the volcano inputs at the last data date, so it ages until new PHIVOLCS data are "
        "added.",
        f"Travel distance is {metrics['allocation']['road_factor']} x the straight-line distance, not a road "
        "network.",
        "Each advisory template was reviewed by one team member.",
    ]
