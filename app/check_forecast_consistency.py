"""Check that the live forecast code reproduces the saved 2026 exposure scores and health impact.

For every 2026 date, the functions in src/forecast.py get the inputs notebook 02 used for that date: the final
SO2 model's forecast made the day before, that date's plume height and earthquake counts, and the historical
hourly wind (data/raw/wind_kanlaon_hourly.csv) in place of the Open-Meteo forecast. A second pass uses the
latest-state inputs of the live forecast (everything known the day before) to show how much they change.

Run from the repository root after app/build_app_data.py:
    .venv\\Scripts\\python app/check_forecast_consistency.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import forecast

RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
APP_DATA = ROOT / "app" / "data"
MODEL_FILE_SUFFIX = {"MLP": "mlp", "LightGBM": "lgbm"}
EXAMPLE_DATE = pd.Timestamp("2026-02-19")
ONE_DAY = pd.Timedelta(days=1)


def show(df, name):
    """Print row count and missing values per column."""
    print(f"{name}: {len(df):,} rows x {df.shape[1]} columns")
    na = df.isna().sum()
    na = na[na > 0]
    print("  missing:", "none" if na.empty else na.to_dict())


metrics = json.loads((APP_DATA / "metrics.json").read_text())
so2_model = joblib.load(APP_DATA / "models"
                        / f"so2_next_day_{MODEL_FILE_SUFFIX[metrics['so2_next_day']['forecast_model']]}.joblib")
exposure_model = joblib.load(APP_DATA / "models"
                             / f"exposure_{MODEL_FILE_SUFFIX[metrics['exposure']['scoring_model']]}.joblib")
q_ref_td = metrics["health_impact"]["q_ref_td"]
activity_cap = metrics["health_impact"]["activity_cap"]
fill_height_m = metrics["plume_index"]["train_median_plume_height_m"]

volcano = pd.read_parquet(APP_DATA / "volcano_daily.parquet").set_index("date")
show(volcano, "volcano_daily")
barangays = (pd.read_parquet(APP_DATA / "barangays.parquet")
             .merge(pd.read_parquet(APP_DATA / "barangay_forecast_inputs.parquet"), on="psgc_code", validate="1:1"))
show(barangays, "barangays + forecast inputs")
wind = pd.read_csv(RAW / "wind_kanlaon_hourly.csv", parse_dates=["time"])
show(wind, "wind_kanlaon_hourly")

saved_so2 = pd.read_csv(PROCESSED / "next_day_forecasts.csv", usecols=["date", "so2_forecast_td"],
                        parse_dates=["date"]).set_index("date")["so2_forecast_td"]
saved_exposure = pd.read_csv(PROCESSED / "exposure_scores.csv", usecols=["psgc_code", "date", "plume_index",
                                                                         "p_exposed"], parse_dates=["date"])
saved_health = pd.read_parquet(APP_DATA / "health_impact.parquet")
saved_shap = pd.read_parquet(APP_DATA / "exposure_shap_top3.parquet")
saved_shap["date"] = pd.to_datetime(saved_shap["date"])
saved = (saved_exposure.merge(saved_health, on=["psgc_code", "date"], how="inner", validate="1:1")
         .merge(saved_shap, on=["psgc_code", "date"], how="inner", validate="1:1"))
show(saved, "saved 2026 barangay-days (exposure, health impact, SHAP)")

# Inputs of notebook 02 per date: SO2 forecast from the day before, same-day plume height, earthquakes and wind
so2_forecast = pd.Series(forecast.forecast_so2_next_day(so2_model, volcano, volcano.index),
                         index=volcano.index + ONE_DAY)
plume_height = volcano["plume_height_median"].fillna(fill_height_m)
daily_wind = forecast.plume_wind(wind, plume_height).reindex(volcano.index)
dates = volcano.index[volcano.index > forecast.TRAIN_END]


def score_day(date, day):
    """Live forecast functions for one date, returned as one row per barangay."""
    scored = forecast.forecast_exposure(barangays, day, exposure_model)
    impact = forecast.main_scenario_impact(barangays.assign(p_exposed=scored["p_exposed"]), day["so2_input_td"],
                                           q_ref_td, activity_cap)
    return scored.join(impact).assign(date=date)


replay_rows, latest_rows = [], []
for date in dates:
    wind_day = daily_wind.loc[date, ["wind_speed_plume", "wind_drift_deg"]].to_dict()
    replay_day = {"so2_input_td": so2_forecast[date], "plume_height_m": plume_height[date], **wind_day,
                  **volcano.loc[date, forecast.EQ_EXPOSURE_COLUMNS].to_dict()}
    replay_rows.append(score_day(date, replay_day))

    state = forecast.latest_state(volcano.loc[:date - ONE_DAY], fill_height_m)
    live_wind = forecast.plume_wind(wind[wind["time"].dt.normalize() == date], state["plume_height_m"])
    latest_day = {"so2_input_td": so2_forecast[date], **state,
                  **live_wind.reindex([date]).iloc[0][["wind_speed_plume", "wind_drift_deg"]].to_dict()}
    latest_rows.append(score_day(date, latest_day))

replay = pd.concat(replay_rows, ignore_index=True)
latest = pd.concat(latest_rows, ignore_index=True)
show(replay, "live code on 2026 dates, notebook inputs")
check = saved.merge(replay, on=["psgc_code", "date"], how="inner", validate="1:1", suffixes=("_saved", "_live"))
show(check, "saved + live")
assert len(check) == len(saved) == len(replay)

so2_gap = (so2_forecast.reindex(dates) - saved_so2.reindex(dates)).abs()
plume_close = np.isclose(check["plume_index_live"], check["plume_index_saved"], rtol=1e-9, atol=0, equal_nan=True)
p_gap = (check["p_exposed_live"] - check["p_exposed_saved"]).abs()
same_level = check["risk_level_live"].astype(str) == check["risk_level_saved"].astype(str)
extra_columns = ["extra_under5_s40", "extra_60plus_s40"]
extra_gap = max((check[f"{c}_live"] - check[f"{c}_saved"]).abs().max()
                / check[f"{c}_saved"].abs().max() for c in extra_columns)
same_features = np.all([check[f"top{k}_feature_live"] == check[f"top{k}_feature_saved"] for k in (1, 2, 3)], axis=0)
shap_gap = max((check[f"top{k}_shap_live"] - check[f"top{k}_shap_saved"]).abs().max() for k in (1, 2, 3))

print(f"\n2026 dates checked: {len(dates)} ({len(check):,} barangay-days)")
print(f"next-day SO2: max difference {so2_gap.max():.3f} t/d (saved values are rounded to 0.1 t/d)")
print(f"plume index: equal within 1e-9 relative on {plume_close.sum():,} of {len(check):,}")
print(f"p_exposed: max absolute difference {p_gap.max():.2e}")
print(f"risk level: same on {same_level.sum():,} of {len(check):,}")
print(f"extra cases: max difference {extra_gap:.2e} of the largest saved value "
      "(saved SO2 forecast rounded to 0.1 t/d, saved cases to 6 significant digits)")
print(f"SHAP top 3 features: same on {same_features.sum():,} of {len(check):,}, max value difference {shap_gap:.4f}")
example = check[check["date"] == EXAMPLE_DATE]
print(f"{EXAMPLE_DATE.date()}: max p_exposed difference {p_gap[example.index].max():.2e}, "
      f"risk level same on {same_level[example.index].sum()} of {len(example)}")
assert so2_gap.max() <= 0.05 + 1e-9
assert plume_close.all() and p_gap.max() < 1e-9 and same_level.all()
assert extra_gap < 1e-4 and same_features.all() and shap_gap <= 1e-4

# How much the live inputs (known the day before) change the scores on the same dates
compare = replay.merge(latest, on=["psgc_code", "date"], validate="1:1", suffixes=("_replay", "_latest"))
level_match = (compare["risk_level_replay"].astype(str) == compare["risk_level_latest"].astype(str)).mean()
p_change = (compare["p_exposed_latest"] - compare["p_exposed_replay"]).abs()
print("\nLatest-state inputs (earthquakes and plume height from the day before, historical wind) against "
      "notebook inputs:")
print(f"p_exposed: mean absolute change {p_change.mean():.3f}, median {p_change.median():.3f}, "
      f"max {p_change.max():.3f}")
print(f"risk level: same on {level_match:.1%} of barangay-days")
