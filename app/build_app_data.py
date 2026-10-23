"""Build the small tables the dashboard reads (app/data) from data/processed, data/raw and results.

Run from the repository root after notebooks 01 to 05:
    .venv\\Scripts\\python app/build_app_data.py
"""
import json
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import allocation

RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REFERENCE = ROOT / "data" / "reference"
REPORT_LOG = ROOT / "data" / "report_log" / "report_log.csv"
RESULTS = ROOT / "results"
MODELS = ROOT / "models"
APP_DATA = ROOT / "app" / "data"
APP_MODELS = APP_DATA / "models"
APP_MODELS.mkdir(parents=True, exist_ok=True)

UTM_CRS = 32651
SIMPLIFY_M = 50
COORD_DECIMALS = 5  # about 1 m
MAX_TOTAL_MB = 50
# same facility types as notebooks 01 and 04
HF_AMENITY = {"hospital", "clinic", "doctors", "health_post"}
HF_HEALTHCARE = {"hospital", "clinic", "doctor"}
BACOLOD_ADM2_PSGC = 630200000
MODEL_FILE_SUFFIX = {"MLP": "mlp", "LightGBM": "lgbm"}


def show(df, name):
    """Print row count and missing values per column."""
    print(f"{name}: {len(df):,} rows x {df.shape[1]} columns")
    na = df.isna().sum()
    na = na[na > 0]
    print("  missing:", "none" if na.empty else na.to_dict())


def save_parquet(df, name):
    """Write a table to app/data as zstd-compressed parquet."""
    df.to_parquet(APP_DATA / f"{name}.parquet", index=False, compression="zstd")


# Barangays
barangays = (pd.read_csv(PROCESSED / "barangays_study_area.csv")
             .rename(columns={"adm4_psgc": "psgc_code", "adm4_en": "barangay"}))
show(barangays, "barangays_study_area")
assert len(barangays) == 216 and barangays["psgc_code"].is_unique

census = pd.read_excel(RAW / "2020-census-total-popn_single-age_malefemale_admin4.xlsx", sheet_name="Brgy_adm4",
                       usecols=["BgyCode_new", "Mun"])
show(census, "census")
census["psgc_code"] = pd.to_numeric(census["BgyCode_new"].str.replace("PH", "", regex=False), errors="coerce")
municipalities = (census[census["psgc_code"].isin(barangays["psgc_code"])]
                  .astype({"psgc_code": "int64"})
                  .rename(columns={"Mun": "municipality"})[["psgc_code", "municipality"]])
show(municipalities, "census rows for study barangays")
barangays = barangays.merge(municipalities, on="psgc_code", how="left", validate="1:1")
show(barangays, "barangays + municipality")

# The nearest facility is searched among all kept facilities in the file, as in notebook 01
hf_zip = (RAW / "hotosm_phl_health_facilities_osm_geojson.zip").as_posix()
hf = gpd.read_file(f"zip://{hf_zip}!health_facilities.geojson")
show(hf.drop(columns="geometry"), "health_facilities")
hf = hf[hf["amenity"].isin(HF_AMENITY) | hf["healthcare"].isin(HF_HEALTHCARE)].to_crs(UTM_CRS)
hf["geometry"] = hf.geometry.centroid
hf = hf.drop_duplicates("id")
hf["facility_type"] = hf["amenity"].fillna(hf["healthcare"])
show(hf[["id", "name", "facility_type"]], "health facilities (kept types, one row per OSM id)")

centroids = gpd.GeoDataFrame(barangays[["psgc_code"]],
                             geometry=gpd.points_from_xy(barangays["centroid_x_utm"], barangays["centroid_y_utm"]),
                             crs=UTM_CRS)
nearest = (gpd.sjoin_nearest(centroids, hf[["name", "facility_type", "geometry"]], distance_col="dist_m")
           .drop_duplicates("psgc_code")
           .rename(columns={"name": "nearest_facility", "facility_type": "nearest_facility_type"}))
barangays = barangays.merge(nearest[["psgc_code", "nearest_facility", "nearest_facility_type", "dist_m"]],
                            on="psgc_code", how="left", validate="1:1")
show(barangays, "barangays + nearest facility")
assert np.allclose(barangays.pop("dist_m") / 1000, barangays["hf_nearest_km"])

BARANGAY_COLUMNS = ["psgc_code", "barangay", "municipality", "province", "centroid_lat", "centroid_lon", "dist_km",
                    "bearing_deg", "pop_total", "pop_under5", "pop_60plus", "nearest_facility",
                    "nearest_facility_type", "hf_nearest_km"]
barangays = barangays[BARANGAY_COLUMNS].rename(columns={"hf_nearest_km": "nearest_facility_km"})
save_parquet(barangays, "barangays")

# Polygons, simplified in metres so the file stays small
polygons = gpd.read_file(RAW / "barangays_negros.geojson")
show(polygons.drop(columns="geometry"), "barangays_negros")
polygons = (polygons[polygons["adm4_psgc"].isin(barangays["psgc_code"])]
            .rename(columns={"adm4_psgc": "psgc_code"})[["psgc_code", "geometry"]]
            .to_crs(UTM_CRS))
polygons["geometry"] = polygons.geometry.simplify(SIMPLIFY_M, preserve_topology=True)
polygons = polygons.to_crs(4326).sort_values("psgc_code", ignore_index=True)
show(polygons.drop(columns="geometry"), "study barangay polygons")
assert len(polygons) == 216 and polygons.geometry.is_valid.all()
polygons.to_file(APP_DATA / "barangay_polygons.geojson", driver="GeoJSON", COORDINATE_PRECISION=COORD_DECIMALS)

# Barangay-day tables
health_impact = pd.read_csv(PROCESSED / "health_impact.csv",
                            usecols=["psgc_code", "date", "report_day", *allocation.MAIN_EXTRA_COLUMNS, "risk_level"],
                            parse_dates=["date"])
show(health_impact, "health_impact")
assert len(health_impact) == 216 * health_impact["date"].nunique()
save_parquet(health_impact.drop(columns="report_day"), "health_impact")

exposure = pd.read_csv(PROCESSED / "exposure_scores.csv", usecols=["psgc_code", "date", "p_exposed", "flagged"],
                       parse_dates=["date"])
show(exposure, "exposure_scores")
exposure = exposure[exposure["date"].isin(health_impact["date"])].reset_index(drop=True)
show(exposure, "exposure_scores on dates with a health impact row")
assert len(exposure) == len(health_impact)
save_parquet(exposure, "exposure_scores")

shap_top3 = pd.read_csv(PROCESSED / "exposure_shap_top3.csv", parse_dates=["date"])
show(shap_top3, "exposure_shap_top3")
save_parquet(shap_top3, "exposure_shap_top3")

# One row per date: forecast and observed SO2, forecast drift, report day
forecasts = pd.read_csv(PROCESSED / "next_day_forecasts.csv",
                        usecols=["date", "so2_forecast_td", "drift_forecast_sector"], parse_dates=["date"])
volcano = (pd.read_csv(PROCESSED / "volcano_daily.csv", usecols=["date", "so2_mean"], parse_dates=["date"])
           .rename(columns={"so2_mean": "so2_observed_td"}))
report_days = health_impact.groupby("date", as_index=False)["report_day"].max()
daily = (report_days.merge(forecasts, on="date", how="left", validate="1:1")
         .merge(volcano, on="date", how="left", validate="1:1"))
show(daily, "daily forecasts")
save_parquet(daily[["date", "so2_forecast_td", "drift_forecast_sector", "so2_observed_td", "report_day"]],
             "daily_forecasts")

# Candidate bases and allocation results
bases = pd.read_csv(PROCESSED / "health_facility_bases.csv")
show(bases, "health_facility_bases")
save_parquet(bases, "health_facility_bases")

for name in ["allocation_comparison", "allocation_grid"]:
    table = pd.read_csv(RESULTS / "tables" / f"{name}.csv")
    show(table, name)
    save_parquet(table, name)

shutil.copyfile(RESULTS / "metrics.json", APP_DATA / "metrics.json")
shutil.copyfile(RESULTS / "forecast_drivers.json", APP_DATA / "forecast_drivers.json")

# Reported barangays per event date, for the replay map
report_log = pd.read_csv(REPORT_LOG, usecols=["event_date", "psgc_code", "hazard"], parse_dates=["event_date"])
report_log["psgc_code"] = report_log["psgc_code"].astype("Int64")
show(report_log, "report_log")
reported = report_log[report_log["psgc_code"].isin(barangays["psgc_code"])]
show(reported, "report_log rows for study barangays")
reported = (reported.assign(ashfall=reported["hazard"].str.contains("ashfall"),
                            sulfur_odor=reported["hazard"].str.contains("sulfur odor"))
            .groupby(["psgc_code", "event_date"], as_index=False)[["ashfall", "sulfur_odor"]].max()
            .rename(columns={"event_date": "date"})
            .astype({"psgc_code": "int64"}))
show(reported, "reported barangay-days")
save_parquet(reported, "reported_barangays")

# Live forecast inputs: the volcano columns the final SO2 and exposure models read, per date
VOLCANO_COLUMNS = (["date", "so2_mean", "so2_last", "so2_days_since", "so2_mean_roll7"]
                   + [f"so2_mean_lag{k}" for k in range(1, 8)]
                   + ["eq_total", "eq_vt", "eq_lfvq", "eq_total_lag1", "eq_total_lag2", "eq_total_lag3",
                      "eq_total_roll7", "plume_height_max", "plume_height_max_roll7", "plume_intensity_max",
                      "ash_plume_obs", "plume_height_median", "drift_obs_sector", "wind_speed_plume",
                      "wind_drift_deg", "wind_speed_10m"])
volcano_state = pd.read_csv(PROCESSED / "volcano_daily.csv", usecols=VOLCANO_COLUMNS, parse_dates=["date"])
show(volcano_state, "volcano_daily (forecast inputs)")
save_parquet(volcano_state[VOLCANO_COLUMNS], "volcano_daily")

# Elevation and baseline rates per barangay; Bacolod City uses its own FHSIS 2022 rates, as in notebook 03
rates = pd.read_csv(REFERENCE / "baseline_rates_fhsis2022.csv").set_index("area")
show(rates, "baseline_rates_fhsis2022")
main_area = rates.index[rates["use"] == "main baseline"].item()
forecast_inputs = (pd.read_csv(PROCESSED / "barangays_study_area.csv", usecols=["adm4_psgc", "adm2_psgc", "elev_m"])
                   .rename(columns={"adm4_psgc": "psgc_code"}))
rate_area = np.where(forecast_inputs.pop("adm2_psgc") == BACOLOD_ADM2_PSGC, "Bacolod City", main_area)
forecast_inputs["y0_under5_per_day"] = rates.loc[rate_area, "ari_under5_per_child_per_year"].to_numpy() / 365
forecast_inputs["y0_all_per_day"] = rates.loc[rate_area, "Y0_per_person_per_day"].to_numpy()
show(forecast_inputs, "barangay forecast inputs")
assert len(forecast_inputs) == 216
save_parquet(forecast_inputs, "barangay_forecast_inputs")

# Final next-day SO2 and exposure models, chosen by 2024-2025 cross-validation
metrics = json.loads((RESULTS / "metrics.json").read_text())
for task, key in [("so2_next_day", "forecast_model"), ("exposure", "scoring_model")]:
    name = f"{task}_{MODEL_FILE_SUFFIX[metrics[task][key]]}.joblib"
    shutil.copyfile(MODELS / name, APP_MODELS / name)
    print("copied", name)

sizes = {path.relative_to(APP_DATA).as_posix(): path.stat().st_size / 1e6
         for path in sorted(APP_DATA.rglob("*")) if path.is_file()}
for name, mb in sizes.items():
    print(f"{name}: {mb:.2f} MB")
print(f"total: {sum(sizes.values()):.2f} MB")
assert sum(sizes.values()) < MAX_TOTAL_MB
