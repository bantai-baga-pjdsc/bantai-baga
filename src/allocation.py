"""Maximum coverage plan for roving medical teams, masks and nebulizer kits.

A base covers a barangay when 1.4 x the straight-line distance from the base to the barangay centroid is at
most max_km. The factor 1.4 is our rough allowance for winding roads; it is not measured.
Barangay weights are extra respiratory consultations (under 5 plus 60 and over) under the main 40 ug/m3 scenario.
Masks go to barangays. Nebulizer kits are used by health workers, so they go to the team bases: each covered
barangay is assigned to its nearest open base. The model plan sizes mask need by pop_total x p_exposed and splits
kits by the weight assigned to each base. The distance-only plan uses no model output: mask need is pop_total and
kits are split by the under-5 and 60+ residents assigned to each base.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

from src.geo import haversine_km

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"

ROAD_FACTOR = 1.4
MAIN_SCENARIO_UGM3 = 40
RANDOM_STATE = 42
# Scenario amounts equal to what DOH distributed after the December 2024 eruption (Bayoran, 2025), not a stock count
SCENARIO_MASKS = 135_000
SCENARIO_KITS = 349
MAIN_EXTRA_COLUMNS = [f"extra_under5_s{MAIN_SCENARIO_UGM3}", f"extra_60plus_s{MAIN_SCENARIO_UGM3}"]
BARANGAY_COLUMNS = ["psgc_code", "centroid_lat", "centroid_lon", "dist_km", "pop_total", "pop_under5", "pop_60plus"]


def road_distance_km(barangays, bases, road_factor=ROAD_FACTOR):
    """Approximate road distance (km): road_factor x great-circle distance, barangays (rows) by bases (columns)."""
    straight_km = haversine_km(barangays["centroid_lat"].to_numpy()[:, None],
                               barangays["centroid_lon"].to_numpy()[:, None],
                               bases["lat"].to_numpy()[None, :], bases["lon"].to_numpy()[None, :])
    return pd.DataFrame(road_factor * straight_km, index=barangays["psgc_code"], columns=bases["base_id"])


def build_plan_inputs(barangays, bases, daily):
    """Plan inputs from barangay, candidate base and barangay-day tables (daily has p_exposed and main extra cases)."""
    barangays = barangays[BARANGAY_COLUMNS].sort_values("psgc_code", ignore_index=True)
    daily = daily.assign(weight=daily[MAIN_EXTRA_COLUMNS].sum(axis=1))
    return {"barangays": barangays, "bases": bases, "daily": daily[["psgc_code", "date", "p_exposed", "weight"]],
            "road_km": road_distance_km(barangays, bases)}


@lru_cache(maxsize=1)
def load_plan_inputs(processed_dir=PROCESSED):
    """Barangays, candidate bases, barangay-day weights and road distances, read from data/processed."""
    barangays = (pd.read_csv(processed_dir / "barangays_study_area.csv",
                             usecols=["adm4_psgc", *BARANGAY_COLUMNS[1:]])
                 .rename(columns={"adm4_psgc": "psgc_code"}))
    bases = pd.read_csv(processed_dir / "health_facility_bases.csv")
    daily = pd.read_csv(processed_dir / "health_impact.csv",
                        usecols=["psgc_code", "date", "p_exposed", *MAIN_EXTRA_COLUMNS], parse_dates=["date"])
    return build_plan_inputs(barangays, bases, daily)


def day_table(date, inputs):
    """One row per study barangay for a date: population, p_exposed, weight and mask need."""
    daily = inputs["daily"]
    day = daily[daily["date"] == pd.Timestamp(date)].drop(columns="date")
    if day.empty:
        raise ValueError(f"no health impact rows for {date}")
    day = inputs["barangays"].merge(day, on="psgc_code", how="left", validate="1:1")
    if day[["p_exposed", "weight"]].isna().any().any():
        raise ValueError(f"missing health impact rows for some barangays on {date}")
    day["mask_need"] = day["pop_total"] * day["p_exposed"]
    return day


def solve_max_coverage(weight, covers, k):
    """Open k bases (columns of the boolean covers table) to maximize the total weight of covered rows; CBC via PuLP."""
    if k > covers.shape[1]:
        raise ValueError(f"k = {k} is more than the {covers.shape[1]} candidate bases")
    weight = np.asarray(weight, dtype=float)
    # rescale so the largest weight is 1; raw weights (about 1e-4) sit close to CBC tolerances
    weight = weight / weight.max() if weight.max() > 0 else weight
    reach = covers.to_numpy()
    rows, cols = range(reach.shape[0]), range(reach.shape[1])

    problem = pulp.LpProblem("max_coverage", pulp.LpMaximize)
    is_open = problem.add_variable_dict("open", cols, cat="Binary")
    is_covered = problem.add_variable_dict("covered", rows, cat="Binary")
    problem += pulp.lpSum([weight[i] * is_covered[i] for i in rows])
    problem += pulp.lpSum(list(is_open.values())) == k
    for i in rows:
        problem += is_covered[i] <= pulp.lpSum([is_open[j] for j in np.flatnonzero(reach[i])])
    stats = problem.solve(pulp.COIN_CMD(msg=False, gapRel=0, gapAbs=0, randomSeed=RANDOM_STATE))
    if stats.status != pulp.LpSolveStatus.Optimal:
        raise RuntimeError(f"maximum coverage problem not solved: {stats.status}")
    return list(covers.columns[[j for j in cols if is_open[j].value() > 0.5]])


def allocate_supplies(need, priority, amount):
    """Integer units per row: up to floor(need) each, highest priority first, until amount runs out."""
    need_units = np.floor(np.asarray(need, dtype=float)).astype(int)
    order = np.argsort(-np.asarray(priority, dtype=float), kind="stable")
    given_before = np.cumsum(need_units[order]) - need_units[order]
    given = np.zeros(len(need_units), dtype=int)
    given[order] = np.clip(amount - given_before, 0, need_units[order])
    return given


def largest_remainder(amount, shares):
    """Split an integer amount in proportion to shares; leftover units go to the largest remainders."""
    shares = np.asarray(shares, dtype=float)
    if shares.sum() <= 0:
        raise ValueError("shares must have a positive total")
    quota = amount * shares / shares.sum()
    given = np.floor(quota).astype(int)
    leftover = amount - given.sum()
    given[np.argsort(-(quota - given), kind="stable")[:leftover]] += 1
    return given


def assemble_plan(day, inputs, chosen, covers, mask_need, mask_priority, kit_basis, masks, kits):
    """Plan dict: chosen bases with their kits, covered PSGC codes, and a barangay table with coverage and masks.

    kit_basis: base column the kits are split by, "weight_assigned" or "vulnerable_assigned".
    """
    in_reach = covers.loc[day["psgc_code"], chosen]
    barangays = day[["psgc_code", "dist_km", "pop_total", "pop_under5", "pop_60plus", "p_exposed", "weight"]].copy()
    barangays["mask_need"] = np.asarray(mask_need, dtype=float)
    barangays["covered"] = in_reach.any(axis=1).to_numpy()
    road_km = inputs["road_km"].loc[day["psgc_code"], chosen]
    barangays["nearest_base_id"] = road_km.idxmin(axis=1).to_numpy()
    barangays["nearest_base_road_km"] = road_km.min(axis=1).to_numpy()
    barangays["masks"] = allocate_supplies(barangays["mask_need"], mask_priority, masks)

    # a barangay in reach of several bases counts once, toward its nearest open base
    assigned = barangays[barangays["covered"]].groupby("nearest_base_id")
    bases = inputs["bases"].set_index("base_id").loc[chosen].reset_index()
    bases["barangays_in_reach"] = in_reach.sum().to_numpy()
    bases["barangays_assigned"] = bases["base_id"].map(assigned.size()).fillna(0).astype(int)
    bases["weight_assigned"] = bases["base_id"].map(assigned["weight"].sum()).fillna(0.0)
    vulnerable = assigned[["pop_under5", "pop_60plus"]].sum().sum(axis=1)
    bases["vulnerable_assigned"] = bases["base_id"].map(vulnerable).fillna(0).astype(int)
    bases["kits"] = largest_remainder(kits, bases[kit_basis])
    return {"bases": bases, "covered": barangays.loc[barangays["covered"], "psgc_code"].tolist(),
            "barangays": barangays}


def make_plan(date, k_teams=5, max_km=10, masks=SCENARIO_MASKS, kits=SCENARIO_KITS, inputs=None):
    """Model plan for one date: maximum coverage bases, masks to the highest weight per resident first."""
    inputs = inputs or load_plan_inputs()
    day = day_table(date, inputs)
    covers = inputs["road_km"] <= max_km
    chosen = solve_max_coverage(day.set_index("psgc_code").loc[covers.index, "weight"], covers, k_teams)
    return assemble_plan(day, inputs, chosen, covers, day["mask_need"], day["weight"] / day["pop_total"],
                         "weight_assigned", masks, kits)


def make_distance_plan(date, k_teams=5, max_km=10, masks=SCENARIO_MASKS, kits=SCENARIO_KITS, inputs=None):
    """Distance-only plan for one date, no model output: k bases nearest the crater, needs from population only."""
    inputs = inputs or load_plan_inputs()
    day = day_table(date, inputs)
    covers = inputs["road_km"] <= max_km
    chosen = inputs["bases"].sort_values(["dist_crater_km", "base_id"]).head(k_teams)["base_id"].tolist()
    return assemble_plan(day, inputs, chosen, covers, day["pop_total"], -day["dist_km"], "vulnerable_assigned",
                         masks, kits)


def vulnerable_covered(plan, psgc_codes):
    """Under-5 and 60+ residents of the given barangays that are inside the plan's coverage."""
    rows = plan["barangays"]
    hit = rows["covered"] & rows["psgc_code"].isin(psgc_codes)
    return int((rows.loc[hit, "pop_under5"] + rows.loc[hit, "pop_60plus"]).sum())


def compare_with_distance_plan(reported, k_teams=5, max_km=10, masks=SCENARIO_MASKS, kits=SCENARIO_KITS,
                               inputs=None):
    """Per report date, vulnerable residents of reported barangays covered by the model and distance-only plans.

    reported: one row per reported barangay-day, with columns date and psgc_code.
    """
    inputs = inputs or load_plan_inputs()
    study = inputs["barangays"]
    rows = []
    for date, group in reported.groupby("date"):
        codes = set(group["psgc_code"]) & set(study["psgc_code"])
        model = make_plan(date, k_teams, max_km, masks, kits, inputs)
        distance = make_distance_plan(date, k_teams, max_km, masks, kits, inputs)
        rows.append({"date": pd.Timestamp(date).date(), "reported_barangays": len(codes),
                     "reported_vulnerable": int(study.loc[study["psgc_code"].isin(codes),
                                                          ["pop_under5", "pop_60plus"]].sum().sum()),
                     "model_plan": vulnerable_covered(model, codes),
                     "distance_plan": vulnerable_covered(distance, codes)})
    comparison = pd.DataFrame(rows)
    comparison["difference"] = comparison["model_plan"] - comparison["distance_plan"]
    return comparison
