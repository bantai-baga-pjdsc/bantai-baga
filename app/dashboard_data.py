"""Data for the dashboard pages: app tables, the live forecast and one table per forecast or replay day."""
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import allocation, forecast, geo, health
from risk_map import PLUME_WIDTH_DEG

DATA = Path(__file__).resolve().parent / "data"

N_BARANGAYS = 216
DATE_MIN = date(2024, 1, 2)
DATE_MAX = date(2026, 10, 20)  # last day with wind data
TEST_START = date(2026, 1, 1)
HORIZONS = ["Tomorrow", "Day 2", "Day 3"]
MODES = ["Daily outlook", "Eruption response"]
TIER_CUTS = [(20, "Top 20"), (60, "Next 40")]
MODEL_FILE_SUFFIX = {"MLP": "mlp", "LightGBM": "lgbm"}

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_TTL_S = 900
WIND_COLUMNS = ["wind_speed_800hPa", "wind_direction_800hPa", "wind_speed_700hPa", "wind_direction_700hPa",
                "geopotential_height_800hPa", "geopotential_height_700hPa"]
MANILA = timezone(timedelta(hours=8), "PHT")  # Asia/Manila has no daylight saving time

DIRECTION_WORDS = {"N": "north", "NE": "northeast", "E": "east", "SE": "southeast", "S": "south",
                   "SW": "southwest", "W": "west", "NW": "northwest"}
FEATURE_WORDS = {
    "dist_km": "Distance from the crater",
    "bearing_sin": "Direction from the crater (east or west side)",
    "bearing_cos": "Direction from the crater (north or south side)",
    "angle_diff_deg": "Angle from the wind-driven plume direction",
    "elev_m": "Elevation",
    "log_plume_index": "Plume model estimate for this barangay",
    "log_so2_input": "SO2 emission level",
    "plume_height_m": "Plume height",
    "wind_speed_plume": "Wind speed at plume height",
    "eq_total_lag1": "Volcanic earthquakes the day before",
    "eq_total_lag2": "Volcanic earthquakes two days before",
    "eq_total_lag3": "Volcanic earthquakes three days before",
    "eq_total_roll7": "Volcanic earthquakes over the past 7 days",
}
ROMAN_NUMERAL = re.compile(r"(X{0,3})(IX|IV|V?I{0,3})")
LOWERCASE_WORDS = {"of"}


def title_case(name):
    """Place name in title case; Roman numerals stay upper case and "of" stays lower case."""
    words = []
    for i, word in enumerate(str(name).split()):
        if ROMAN_NUMERAL.fullmatch(word):
            words.append(word)
        elif i > 0 and word.lower() in LOWERCASE_WORDS:
            words.append(word.lower())
        else:
            first = next((j for j, ch in enumerate(word) if ch.isalpha()), 0)
            words.append(word[:first] + word[first:].capitalize())
    return " ".join(words)


def facility_label(name, facility_type):
    """Facility name, or its type when OpenStreetMap has no name."""
    if isinstance(name, str) and name.strip():
        return name
    return f"Unnamed health facility ({str(facility_type).replace('_', ' ')})"


def long_date(day):
    """Date as "Saturday, October 24, 2026"."""
    return f"{day:%A, %B} {day.day}, {day.year}"


def short_date(day):
    """Date as "October 24, 2026"."""
    return f"{day:%B} {day.day}, {day.year}"


def direction_words(drift_deg):
    """Compass direction in words (8 sectors) for a drift in degrees."""
    return DIRECTION_WORDS[geo.deg_to_sector(drift_deg)]


# Loading

@st.cache_data
def load_barangays():
    """Study barangays with display names, population and nearest facility."""
    barangays = pd.read_parquet(DATA / "barangays.parquet")
    barangays["name"] = barangays["barangay"].map(title_case)
    barangays["municipality_name"] = barangays["municipality"].map(title_case)
    barangays["nearest_facility_name"] = [facility_label(n, t) for n, t in
                                          zip(barangays["nearest_facility"], barangays["nearest_facility_type"])]
    return barangays


@st.cache_data
def load_polygons():
    """Simplified barangay polygons as a GeoJSON dict."""
    return json.loads((DATA / "barangay_polygons.geojson").read_text(encoding="utf-8"))


@st.cache_data
def load_barangay_days():
    """Barangay-day exposure scores, risk levels and main-scenario extra cases."""
    impact = pd.read_parquet(DATA / "health_impact.parquet")
    exposure = pd.read_parquet(DATA / "exposure_scores.parquet")
    days = impact.merge(exposure, on=["psgc_code", "date"], how="left", validate="1:1")
    days["date"] = pd.to_datetime(days["date"])
    return days


@st.cache_data
def load_shap():
    """Top 3 SHAP features per barangay-day (2026 only)."""
    shap_top3 = pd.read_parquet(DATA / "exposure_shap_top3.parquet")
    shap_top3["date"] = pd.to_datetime(shap_top3["date"])
    return shap_top3


@st.cache_data
def load_daily():
    """Forecast and observed SO2, forecast drift and report day per date."""
    daily = pd.read_parquet(DATA / "daily_forecasts.parquet")
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.set_index("date")


@st.cache_data
def load_volcano():
    """Daily volcano inputs of the live forecast (SO2, earthquakes, plume height), observed drift and plume wind."""
    return pd.read_parquet(DATA / "volcano_daily.parquet").set_index("date")


@st.cache_data
def load_reported():
    """Study barangays with an ashfall or sulfur odor report, per event date."""
    return pd.read_parquet(DATA / "reported_barangays.parquet")


@st.cache_data
def load_bases():
    """Candidate team bases (health facilities)."""
    bases = pd.read_parquet(DATA / "health_facility_bases.parquet")
    bases["label"] = [facility_label(n, t) for n, t in zip(bases["name"], bases["amenity"])]
    return bases


@st.cache_data
def load_table(name):
    """A small parquet table from app/data."""
    return pd.read_parquet(DATA / f"{name}.parquet")


@st.cache_data
def load_metrics():
    """Model and plan results saved by the notebooks."""
    return json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))


@st.cache_data
def load_drivers():
    """SHAP shares, plume wedge effect, report alignment, plume heights and upper-wind check (notebook 05)."""
    return json.loads((DATA / "forecast_drivers.json").read_text(encoding="utf-8"))


@st.cache_data
def load_templates():
    """Advisory templates, one per risk level and language."""
    return pd.read_csv(DATA / "advisory_templates.csv", dtype=str, keep_default_na=False)


@st.cache_resource
def load_models():
    """Final next-day SO2 model and final exposure model, chosen by 2024-2025 cross-validation."""
    metrics = load_metrics()
    so2_name = MODEL_FILE_SUFFIX[metrics["so2_next_day"]["forecast_model"]]
    exposure_name = MODEL_FILE_SUFFIX[metrics["exposure"]["scoring_model"]]
    return (joblib.load(DATA / "models" / f"so2_next_day_{so2_name}.joblib"),
            joblib.load(DATA / "models" / f"exposure_{exposure_name}.joblib"))


# Live forecast

# Failures are cached too, for FORECAST_TTL_S, so an unreachable API does not slow every rerun
@st.cache_data(ttl=FORECAST_TTL_S, show_spinner="Getting the wind forecast from Open-Meteo")
def live_forecast():
    """Risk per barangay for the next 3 days from the latest volcano state and the Open-Meteo wind forecast.

    Returns None when the forecast cannot be loaded or lacks one of the 3 days.
    """
    params = {"latitude": geo.CRATER_LAT, "longitude": geo.CRATER_LON, "hourly": ",".join(WIND_COLUMNS),
              "wind_speed_unit": "ms", "timezone": "Asia/Manila", "forecast_days": len(HORIZONS) + 1}
    try:
        response = requests.get(FORECAST_URL, params=params, timeout=10)
        response.raise_for_status()
        hourly = pd.DataFrame(response.json()["hourly"])[["time", *WIND_COLUMNS]]
    except (requests.RequestException, ValueError, KeyError):
        return None
    fetched_at = datetime.now(MANILA)
    hourly["time"] = pd.to_datetime(hourly["time"])
    days = [pd.Timestamp(fetched_at.date()) + pd.Timedelta(days=k) for k in range(1, len(HORIZONS) + 1)]

    metrics = load_metrics()
    volcano = load_volcano()
    so2_model, exposure_model = load_models()
    last_date = volcano.index[-1]
    so2_td = float(forecast.forecast_so2_next_day(so2_model, volcano, [last_date])[0])
    state = forecast.latest_state(volcano, metrics["plume_index"]["train_median_plume_height_m"])
    wind = forecast.plume_wind(hourly, state["plume_height_m"]).reindex(days)
    if wind[["wind_speed_plume", "wind_drift_deg"]].isna().any().any():
        return None

    barangays = load_barangays().merge(load_table("barangay_forecast_inputs"), on="psgc_code", validate="1:1")
    health_settings = metrics["health_impact"]
    rows = {}
    for day in days:
        inputs = {"so2_input_td": so2_td, **state, **wind.loc[day, ["wind_speed_plume", "wind_drift_deg"]]}
        scored = forecast.forecast_exposure(barangays, inputs, exposure_model)
        impact = forecast.main_scenario_impact(barangays.assign(p_exposed=scored["p_exposed"]), so2_td,
                                               health_settings["q_ref_td"], health_settings["activity_cap"])
        rows[day] = scored.join(impact).drop(columns=["dist_km", "bearing_deg"])
    return {"days": days, "rows": rows, "wind": wind, "so2_td": so2_td, "state": state,
            "last_data_date": last_date, "fetched_at": fetched_at}


# One table per day

def shap_reasons(row):
    """Top 3 SHAP features of a barangay-day in plain words."""
    reasons = []
    for k in (1, 2, 3):
        feature, value = row[f"top{k}_feature"], row[f"top{k}_shap"]
        if isinstance(feature, str):
            effect = "raised" if value > 0 else "lowered"
            reasons.append(f"{FEATURE_WORDS.get(feature, feature)} {effect} the chance")
    return reasons


def finish_rows(day_rows, so2_td, drift_deg):
    """One row per study barangay with names, SHAP reasons, rise in risk, extra cases, downwind flag and list ranks.

    so2_td is the day's forecast SO2; the rise in risk (pct_rise_s40) and the whole-barangay extra cases
    (extra_all_s40) follow notebook 03. A barangay is downwind when its centroid lies inside the forecast plume
    wedge drawn on the map (drift_deg, None when there is no drift forecast).
    """
    rows = (load_barangays().merge(day_rows, on="psgc_code", how="left", validate="1:1")
            .merge(load_table("barangay_forecast_inputs")[["psgc_code", "y0_all_per_day"]], on="psgc_code",
                   how="left", validate="1:1"))
    rows["risk_level"] = pd.Categorical(rows["risk_level"].astype(str), categories=health.RISK_LEVELS, ordered=True)
    rows["reasons"] = rows.apply(shap_reasons, axis=1)
    settings = load_metrics()["health_impact"]
    delta_c = (rows["p_exposed"] * health.activity_factor(so2_td, settings["q_ref_td"], settings["activity_cap"])
               * settings["main_scenario_ugm3"])
    rows["pct_rise_s40"] = health.relative_increase(delta_c) * 100
    rows["extra_all_s40"] = health.extra_cases(rows["pop_total"], rows["y0_all_per_day"], delta_c)
    rows["nearest_facility_text"] = [f"{name}, {km:.1f} km" for name, km in
                                     zip(rows["nearest_facility_name"], rows["nearest_facility_km"])]
    rows["extra_under5"] = rows[allocation.MAIN_EXTRA_COLUMNS[0]]
    rows["extra_60plus"] = rows[allocation.MAIN_EXTRA_COLUMNS[1]]
    rows["extra_under5_60plus"] = rows["extra_under5"] + rows["extra_60plus"]
    rows["pop_vulnerable"] = rows["pop_under5"] + rows["pop_60plus"]
    rows["downwind"] = (False if drift_deg is None or pd.isna(drift_deg)
                        else geo.angle_diff_deg(rows["bearing_deg"], drift_deg) <= PLUME_WIDTH_DEG / 2)
    # daily outlook list: highest risk level first, downwind first within a level, then the most expected extra cases
    rows["risk_rank"] = list_rank(rows.assign(level_code=rows["risk_level"].cat.codes),
                                  ["level_code", "downwind", "extra_under5_60plus"])
    # eruption response: the map tier from the chance of being reached, then the young children and older adults
    rows["exposure_rank"] = rows["p_exposed"].rank(ascending=False, method="first").astype(int)
    rows["exposure_tier"] = np.select([rows["exposure_rank"] <= cut for cut, _ in TIER_CUTS],
                                      [label for _, label in TIER_CUTS], default="Rest")
    tier_order = {label: len(TIER_CUTS) - i for i, (_, label) in enumerate(TIER_CUTS)}
    rows["priority_rank"] = list_rank(rows.assign(tier_code=rows["exposure_tier"].map(tier_order).fillna(0)),
                                      ["tier_code", "pop_vulnerable", "downwind"])
    return rows


def list_rank(rows, keys):
    """Rank 1 to n by the keys, each largest first, with the PSGC code breaking any remaining tie."""
    order = rows.sort_values([*keys, "psgc_code"], ascending=[False] * len(keys) + [True]).index
    return pd.Series(np.arange(1, len(rows) + 1), index=order).reindex(rows.index)


@st.cache_data
def replay_rows(day):
    """Saved model outputs for a past date, one row per study barangay."""
    ts = pd.Timestamp(day)
    days, shap_top3 = load_barangay_days(), load_shap()
    day_rows = (days[days["date"] == ts].drop(columns="date")
                .merge(shap_top3[shap_top3["date"] == ts].drop(columns="date"), on="psgc_code", how="left",
                       validate="1:1"))
    return finish_rows(day_rows, load_daily().loc[ts, "so2_forecast_td"], load_volcano().loc[ts, "wind_drift_deg"])


def forecast_view(live, horizon):
    """What the pages show for one live forecast day."""
    day = live["days"][HORIZONS.index(horizon)]
    wind = live["wind"].loc[day]
    metrics = load_metrics()
    return {
        "source": "forecast", "day": day.date(), "horizon": horizon,
        "rows": finish_rows(live["rows"][day], live["so2_td"], wind["wind_drift_deg"]),
        "so2_td": live["so2_td"], "drift_deg": wind["wind_drift_deg"], "wind_speed": wind["wind_speed_plume"],
        "so2_model": metrics["so2_next_day"]["forecast_model"], "last_data_date": live["last_data_date"].date(),
        "fetched_at": live["fetched_at"], "observed_deg": None, "observed_so2": None, "reported": frozenset(),
    }


def replay_view(day):
    """What the pages show for one past date.

    The plume wedge follows that day's wind at plume height, the direction the saved exposure scores used; the
    final drift model's forecast is shown as text only.
    """
    ts = pd.Timestamp(day)
    daily, volcano, metrics = load_daily().loc[ts], load_volcano().loc[ts], load_metrics()
    reported = load_reported()
    observed_sector = volcano["drift_obs_sector"]
    model_sector = daily["drift_forecast_sector"]
    return {
        "source": "replay", "day": day, "horizon": None, "rows": replay_rows(day),
        "so2_td": daily["so2_forecast_td"],
        "drift_deg": volcano["wind_drift_deg"] if pd.notna(volcano["wind_drift_deg"]) else None,
        "wind_speed": volcano["wind_speed_plume"],
        "drift_model": metrics["drift_next_day"]["forecast_model"],
        "drift_model_deg": geo.SECTOR_DEG[model_sector] if isinstance(model_sector, str) else None,
        "so2_model": metrics["so2_next_day"]["forecast_model"],
        "observed_deg": geo.SECTOR_DEG[observed_sector] if isinstance(observed_sector, str) else None,
        "observed_so2": daily["so2_observed_td"],
        "reported": frozenset(reported.loc[reported["date"] == ts, "psgc_code"]),
    }


def set_focus(view):
    """Remember the day on screen, so the response planner and barangay list use the same day."""
    st.session_state["focus"] = {"source": view["source"], "day": view["day"], "horizon": view["horizon"]}


def focus_view():
    """The forecast day or replay date last opened on Forecast or Replay past events (tomorrow by default)."""
    focus = st.session_state.get("focus", {"source": "forecast", "horizon": HORIZONS[0]})
    if focus["source"] == "forecast":
        live = live_forecast()
        if live is not None:
            return forecast_view(live, focus["horizon"])
        return replay_view(DATE_MAX)
    return replay_view(focus["day"])


def view_title(view):
    """Short description of the day on screen, such as "Forecast for tomorrow, Saturday, October 24, 2026"."""
    if view["source"] == "forecast":
        prefix = "Forecast for tomorrow" if view["horizon"] == HORIZONS[0] else f"Forecast for {view['horizon']}"
        return f"{prefix}, {long_date(view['day'])}"
    return f"Replay of {long_date(view['day'])}"


def mode_selected():
    """Current mode (Daily outlook or Eruption response), shared by every page."""
    return st.session_state.get("mode") or MODES[0]


# Response plan

def plan_day_rows(view):
    """make_plan inputs for the day on screen: p_exposed and main-scenario extra cases per barangay."""
    return (view["rows"][["psgc_code", "p_exposed", *allocation.MAIN_EXTRA_COLUMNS]]
            .assign(date=pd.Timestamp(view["day"])))


@st.cache_data(show_spinner="Solving the response plan")
def response_plan(day_rows, k_teams=5, max_km=10, masks=allocation.SCENARIO_MASKS, kits=allocation.SCENARIO_KITS,
                  unavailable=()):
    """Model plan for one day: team bases, kits per base and masks per barangay; unavailable bases are left out."""
    bases = load_bases()
    inputs = allocation.build_plan_inputs(load_barangays(), bases[~bases["base_id"].isin(unavailable)], day_rows)
    return allocation.make_plan(day_rows["date"].iloc[0], k_teams, max_km, masks, kits, inputs=inputs)


@st.cache_data
def barangays_out_of_reach(max_km, unavailable=()):
    """Barangays farther than max_km (approximate road distance) from every available candidate base."""
    bases = load_bases()
    road_km = allocation.road_distance_km(load_barangays(), bases[~bases["base_id"].isin(unavailable)])
    return int((~(road_km <= max_km).any(axis=1)).sum())
