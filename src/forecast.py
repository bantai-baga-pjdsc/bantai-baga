"""Exposure forecast for one day from volcano inputs and hourly wind, with the feature code of notebook 02.

Per day the inputs are next-day SO2 (t/d), plume height above the crater (m), earthquake counts (lags 1 to 3 and
the 7-day mean) and hourly 800/700 hPa wind at the crater. The outputs per barangay are the plume index, the
exposure probability, the top 3 SHAP features and the main-scenario health impact of notebook 03.
"""
import numpy as np
import pandas as pd

from src import geo, health, plume

TRAIN_END = pd.Timestamp("2025-12-31")
DAYTIME_HOURS = (6, 18)  # inclusive, Asia/Manila time, as in notebook 01
MAIN_SCENARIO_UGM3 = health.WHO_SO2_24H_UGM3

EQ_LOG_COLUMNS = ["eq_total", "eq_vt", "eq_lfvq", "eq_total_lag1", "eq_total_lag2", "eq_total_roll7"]
SO2_FEATURES = (["log_so2_today", "log_so2_last", "so2_days_since", "log_so2_roll7"]
                + [f"log_so2_lag{k}" for k in range(1, 8)]
                + [f"log_{col}" for col in EQ_LOG_COLUMNS]
                + ["plume_height_max", "plume_height_max_roll7", "plume_intensity_max", "ash_plume_obs",
                   "wind_speed_plume", "wind_speed_10m"])
EQ_EXPOSURE_COLUMNS = ["eq_total_lag1", "eq_total_lag2", "eq_total_lag3", "eq_total_roll7"]
EXPOSURE_FEATURES = ["dist_km", "bearing_sin", "bearing_cos", "angle_diff_deg", "elev_m", "log_plume_index",
                     "log_so2_input", "plume_height_m", "wind_speed_plume", *EQ_EXPOSURE_COLUMNS]


def so2_features(volcano):
    """Next-day SO2 model inputs per date (the row for day t forecasts day t+1)."""
    features = pd.DataFrame({
        "log_so2_today": np.log1p(volcano["so2_mean"]),
        "log_so2_last": np.log1p(volcano["so2_last"]),
        "so2_days_since": volcano["so2_days_since"],
        "log_so2_roll7": np.log1p(volcano["so2_mean_roll7"]),
        **{f"log_so2_lag{k}": np.log1p(volcano[f"so2_mean_lag{k}"]) for k in range(1, 8)},
        **{f"log_{col}": np.log1p(volcano[col]) for col in EQ_LOG_COLUMNS},
    }, index=volcano.index)
    for col in SO2_FEATURES[-6:]:
        features[col] = volcano[col]
    return features[SO2_FEATURES]


def so2_log_range(volcano):
    """Range of log1p daily SO2 on the 2024-2025 target days, which bounds every forecast."""
    target = np.log1p(volcano.loc[volcano.index[1]:TRAIN_END, "so2_mean"].dropna())
    return target.min(), target.max()


def forecast_so2_next_day(model, volcano, dates):
    """Next-day SO2 (t/d) from the volcano rows of the given dates."""
    log_so2 = model.predict(so2_features(volcano.loc[dates]))
    return np.expm1(np.clip(log_so2, *so2_log_range(volcano)))


def latest_state(volcano, fill_plume_height_m):
    """Inputs held at the last volcano date for every forecast day: earthquake counts and plume height.

    The day after the last date sees that date's count as lag 1; the 7-day mean ends on the last date.
    """
    last = volcano.iloc[-1]
    height = last["plume_height_median"]
    return {"eq_total_lag1": last["eq_total"], "eq_total_lag2": last["eq_total_lag1"],
            "eq_total_lag3": last["eq_total_lag2"], "eq_total_roll7": last["eq_total_roll7"],
            "plume_height_m": fill_plume_height_m if pd.isna(height) else height}


def plume_wind(hourly, plume_height_m):
    """Daily plume-level wind speed and drift (degrees toward) from hourly wind between 06:00 and 18:00.

    plume_height_m is the plume height above the crater: one value, or a Series indexed by date.
    """
    hours = hourly[hourly["time"].dt.hour.between(*DAYTIME_HOURS)]
    hours = hours.assign(date=hours["time"].dt.normalize())
    if not isinstance(plume_height_m, pd.Series):
        plume_height_m = pd.Series(plume_height_m, index=hours["date"].unique())
    return geo.daily_plume_wind(hours, geo.CRATER_ELEV_M + plume_height_m)


def exposure_inputs(barangays, day):
    """Plume index and exposure model inputs per barangay for one day.

    barangays: psgc_code, dist_km, bearing_deg, elev_m. day: so2_input_td, plume_height_m, wind_speed_plume,
    wind_drift_deg and the earthquake columns.
    """
    rows = barangays[["psgc_code", "dist_km", "bearing_deg", "elev_m"]].copy()
    rows["angle_diff_deg"] = geo.angle_diff_deg(rows["bearing_deg"], day["wind_drift_deg"])
    rows["plume_index"] = plume.compute_plume_index(
        day["so2_input_td"], day["wind_speed_plume"], day["plume_height_m"], rows["elev_m"], rows["dist_km"],
        rows["angle_diff_deg"], terrain="following")
    # without wind the angle is unknown, and compute_plume_index would return 0 instead of a missing value
    rows.loc[rows["angle_diff_deg"].isna(), "plume_index"] = np.nan
    bearing_rad = np.radians(rows["bearing_deg"])
    rows["bearing_sin"] = np.sin(bearing_rad)
    rows["bearing_cos"] = np.cos(bearing_rad)
    rows["log_plume_index"] = np.log1p(rows["plume_index"])
    rows["log_so2_input"] = np.log1p(day["so2_input_td"])
    for col in ["plume_height_m", "wind_speed_plume", *EQ_EXPOSURE_COLUMNS]:
        rows[col] = float(day[col])
    return rows


def shap_top3(model, features):
    """Top 3 features by absolute SHAP value (log-odds) per row, from LightGBM's built-in TreeSHAP."""
    contributions = model.predict(features, pred_contrib=True)[:, :-1]
    top_idx = np.argsort(-np.abs(contributions), axis=1)[:, :3]
    rows = np.arange(len(features))
    names = np.array(features.columns)
    top3 = {}
    for k in range(3):
        top3[f"top{k + 1}_feature"] = names[top_idx[:, k]]
        top3[f"top{k + 1}_shap"] = contributions[rows, top_idx[:, k]].round(4)
    return pd.DataFrame(top3, index=features.index)


def forecast_exposure(barangays, day, model):
    """Exposure inputs, probability (p_exposed) and top 3 SHAP features per barangay for one day."""
    rows = exposure_inputs(barangays, day)
    features = rows[EXPOSURE_FEATURES]
    rows["p_exposed"] = model.predict_proba(features)[:, 1]
    return rows.join(shap_top3(model, features))


def main_scenario_impact(rows, so2_td, q_ref_td, activity_cap, scenario_ugm3=MAIN_SCENARIO_UGM3):
    """SO2 increase, extra cases per day (under 5 and 60+) and risk level per barangay, as in notebook 03.

    rows: p_exposed, pop_under5, pop_60plus, y0_under5_per_day and y0_all_per_day per barangay.
    """
    delta_c = rows["p_exposed"] * health.activity_factor(so2_td, q_ref_td, activity_cap) * scenario_ugm3
    return pd.DataFrame({
        f"delta_c_ugm3_s{scenario_ugm3}": delta_c,
        f"extra_under5_s{scenario_ugm3}": health.extra_cases(rows["pop_under5"], rows["y0_under5_per_day"], delta_c),
        f"extra_60plus_s{scenario_ugm3}": health.extra_cases(rows["pop_60plus"], rows["y0_all_per_day"], delta_c),
        "risk_level": health.risk_level(delta_c),
    }, index=rows.index)
