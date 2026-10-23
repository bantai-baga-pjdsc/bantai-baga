"""Rewrite the generated parts of README.md from results/metrics.json and results/tables.

Each generated part sits between <!-- RESULTS:START name --> and <!-- RESULTS:END name --> markers; the rest of
README.md is left as written. Run from the repository root:
    python scripts/update_readme.py          rewrite the generated parts
    python scripts/update_readme.py --check  exit with an error if README.md is out of date
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import results_summary

README = ROOT / "README.md"
RESULTS = ROOT / "results"
BLOCK = re.compile(r"(<!-- RESULTS:START (?P<name>[a-z_]+) -->\n).*?(<!-- RESULTS:END (?P=name) -->)", re.S)
# the README marks each target Met or Missed for the final model; the dashboard also shows the comparison model
FINAL_MODEL_STATUS = {"Met by both": "Met", "Met by final model only": "Met", "Missed by both": "Missed",
                      "Met by comparison model only": "Missed"}


def markdown_table(df):
    """DataFrame as a GitHub Markdown table."""
    cells = df.astype(str).map(lambda text: text.replace("|", "\\|"))
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(row) + " |" for row in cells.itertuples(index=False)]
    return "\n".join(lines)


def results_block(metrics, coverage):
    """2026 test results against our original targets, the plan comparison and the settings used."""
    exposure, plan, health = metrics["exposure"], metrics["allocation"], metrics["health_impact"]
    models = results_summary.model_results_table(metrics)
    models["Status"] = models["Status"].replace(FINAL_MODEL_STATUS)
    models = models.rename(columns={results_summary.FINAL_MODEL_LABEL: "Final model"})
    coverage = coverage.rename(columns={
        "date": "Date", "reported_barangays": "Reported barangays",
        "reported_vulnerable": "Under 5 and 60+ in reported barangays", "model_plan": "Covered, model plan",
        "distance_plan": "Covered, distance-only plan", "difference": "Difference"})
    for column in coverage.columns[1:]:
        coverage[column] = coverage[column].map("{:,}".format)
    return "\n\n".join([
        f"The 2026 test covers {metrics['drift_next_day']['n_test']:,} days with an observed drift, "
        f"{metrics['so2_next_day']['n_test']:,} days with a measured next-day SO2 emission, and "
        f"{len(exposure['test_event_dates'])} event days with {exposure['n_test']:,} barangay-days and "
        f"{exposure['n_test_exposed']} reported exposures. Status refers to the final model.",
        markdown_table(models),
        f"Response plan on the {plan['report_days']} report days of 2026, with {plan['k_teams']} roving teams, a "
        f"{plan['max_km']} km travel limit, {plan['scenario_masks']:,} masks and {plan['scenario_kits']:,} "
        f"nebulizer kits. The model plan uses the final exposure model ({exposure['scoring_model']}).",
        markdown_table(results_summary.plan_results_table(metrics)),
        "<details>\n<summary>Team coverage per 2026 report day</summary>\n\n" + markdown_table(coverage)
        + "\n\n</details>",
        f"Settings: RR = {health['rr_per_10ugm3']} per 10 µg/m³ of 24-hour SO2 (Carlsen et al., 2021); q_ref = "
        f"{health['q_ref_td']:,.0f} t/d, the median SO2 on the {health['q_ref_n_days']} report days of 2024-2025 "
        f"with an SO2 reading; c = {health['activity_cap']}; main scenario S = {health['main_scenario_ugm3']} µg/m³.",
    ])


def limitations_block(metrics):
    """Limitations, the same list as the Methods & results page."""
    return "\n".join(f"- {item}" for item in results_summary.limitations(metrics))


def render(text, blocks):
    """README text with every marked part replaced by its generated content."""
    found = [m["name"] for m in BLOCK.finditer(text)]
    if sorted(found) != sorted(blocks):
        raise SystemExit(f"README.md markers {found} do not match the generated parts {sorted(blocks)}")
    return BLOCK.sub(lambda m: f"{m[1]}\n{blocks[m['name']]}\n\n{m[3]}", text)


def main():
    """Rewrite the generated parts of README.md, or with --check only report whether they are up to date."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only check that README.md is up to date")
    args = parser.parse_args()

    metrics = json.loads((RESULTS / "metrics.json").read_text(encoding="utf-8"))
    coverage = pd.read_csv(RESULTS / "tables" / "allocation_comparison.csv")
    blocks = {"results": results_block(metrics, coverage), "limitations": limitations_block(metrics)}
    current = README.read_text(encoding="utf-8")
    updated = render(current, blocks)

    if args.check:
        if updated != current:
            raise SystemExit("README.md is out of date. Run: python scripts/update_readme.py")
        print("README.md is up to date")
        return
    README.write_text(updated, encoding="utf-8", newline="\n")
    print("README.md updated" if updated != current else "README.md already up to date")


if __name__ == "__main__":
    main()
