"""Methods & results: 2026 results against our original targets, the live forecast, data sources and limitations."""
import pandas as pd
import streamlit as st

import dashboard_data as dd
from src.results_summary import limitations, model_results_table, plan_results_table

SOURCES = [
    ("PHIVOLCS (2026). Kanlaon SO2 flux, visual observation and daily earthquake count records.",
     "https://wovodat.phivolcs.dost.gov.ph/data/download"),
    ("Open-Meteo (2026). Historical forecast API, hourly wind at 800 and 700 hPa (600 and 500 hPa for the "
     "upper-level wind check).",
     "https://open-meteo.com/en/docs/historical-forecast-api"),
    ("Open-Meteo. Forecast API, used for the live 3-day forecast.", "https://open-meteo.com/en/docs"),
    ("NASA Jet Propulsion Laboratory (2013). SRTM Global 1 arc second, version 3.",
     "https://doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003"),
    ("Philippine Statistics Authority (2023). Population by single-year age, sex and barangay, Census 2020.",
     "https://data.humdata.org/dataset/popn-single-year-age-sex-and-barangay-census-2020"),
    ("Faeldon, J. (2024). Philippines JSON maps (barangay boundaries).",
     "https://github.com/faeldon/philippines-json-maps"),
    ("Humanitarian OpenStreetMap Team (2026). Philippines health facilities (OpenStreetMap export).",
     "https://data.humdata.org/dataset/hotosm_phl_health_facilities"),
    ("Carlsen et al. (2021). Severe volcanic SO2 exposure and respiratory morbidity in the Icelandic population. "
     "Source of RR = 1.0126 per 10 µg/m³.", "https://doi.org/10.1186/s12940-021-00698-y"),
    ("World Health Organization (2021). WHO global air quality guidelines (24-hour SO2 guideline of 40 µg/m³).",
     "https://iris.who.int/handle/10665/345329"),
    ("Bayoran, G. P. (2025). Respiratory infection, other illness hit Kanlaon-displaced residents. Negros Now "
     "Daily. Source of the 135,000 masks and 349 nebulizer kits scenario.",
     "https://negrosnowdaily.com/respiratory-infection-other-illness-hit-kanlaon-displaced-residents/"),
]


metrics = dd.load_metrics()
exposure, plan, health_settings = metrics["exposure"], metrics["allocation"], metrics["health_impact"]
st.html('<div class="bb-title">Methods & results</div><div class="bb-subtitle">How BantAI Baga works, how well it '
        'did on 2026 data, and what it cannot do</div>')

st.subheader("2026 test results")
st.caption("Final models were selected by cross-validation on 2024-2025 data before evaluating on 2026. The "
           "comparison model is the other candidate (gradient boosting with LightGBM, or a small neural network, "
           f"MLP). The exposure test covers {len(exposure['test_event_dates'])} event days, "
           f"{exposure['n_test']:,} barangay-days and {exposure['n_test_exposed']} reported exposures. Replay dates "
           "in 2024-2025 are in-sample.")
st.table(model_results_table(metrics), hide_index=True)
st.caption(f"Response plan on the 2026 report days ({plan['report_days']} days), with {plan['k_teams']} teams, a "
           f"{plan['max_km']} km travel limit and the scenario supplies. The model plan uses the final exposure "
           f"model ({exposure['scoring_model']}).")
st.table(plan_results_table(metrics), hide_index=True)
# 254,237 is from the first distance-only plan, which used model-based needs (notebook 04, Limitations)
st.caption("Masks are about the same for both plans: with the distance-only plan's first, model-based needs, it sent "
           "254,237 masks to reported barangays. We report masks without a target.")

with st.expander("Team coverage per 2026 report day"):
    st.dataframe(dd.load_table("allocation_comparison"), hide_index=True, width="stretch",
                 column_config={"date": "Date", "reported_barangays": "Reported barangays",
                                "reported_vulnerable": "Under 5 and 60+ in reported barangays",
                                "model_plan": "Covered, model plan", "distance_plan": "Covered, distance-only",
                                "difference": "Difference"})
with st.expander("Team coverage for other team counts and travel limits"):
    st.dataframe(dd.load_table("allocation_grid"), hide_index=True, width="stretch",
                 column_config={"k_teams": "Teams", "max_km": "Travel limit (km)",
                                "report_days": "Report days", "model_plan": "Covered, model plan",
                                "distance_plan": "Covered, distance-only", "difference": "Difference",
                                "days_model_more": "Days model covers more", "days_tied": "Days tied",
                                "days_distance_more": "Days distance-only covers more"})

drivers = dd.load_drivers()
shares = drivers["shap_group_share_2026"]
wedge_far, wedge_near = drivers["wedge_effect_2026"]["10-30 km"], drivers["wedge_effect_2026"]["0-10 km"]
in_wedge = drivers["reports_modeled_wedge"]
heights = drivers["plume_height_m"]
upper = drivers["upper_wind"]
upper_share, upper_km = upper["share_within_45deg"], {k: v / 1000 for k, v in upper["altitude_m"].items()}
upper_verdict = ("The 600 or 500 hPa wind fits at least as well, so the eruption-response map adds it as guidance."
                 if upper["upper_matches_at_least_as_well"] else
                 "Both higher levels fit worse than the wind we use, so the dashboard shows no upper-level wind.")
st.subheader("What drives the forecast")
st.markdown(
    f"- Fixed geography carries most of the exposure model's output. Of the mean absolute SHAP value on 2026 "
    f"barangay-days, {shares['fixed geography']:.0%} comes from distance, direction and elevation, "
    f"{shares['wind and plume']:.0%} from wind direction and the plume, and {shares['earthquakes']:.0%} from "
    f"earthquakes ({shares['SO2 and plume height']:.0%} from SO2 and plume height). Earthquake counts are the same "
    "for every barangay on a day, so they raise or lower the whole map.\n"
    f"- The plume wedge matters most away from the crater. On 2026 days, mean p_exposed 10 to 30 km from the "
    f"crater was {wedge_far['mean_p_inside']:.2f} inside the 45-degree wedge of the modeled wind and "
    f"{wedge_far['mean_p_outside']:.2f} outside, {wedge_far['ratio']:.1f} times higher. Within 10 km it was "
    f"{wedge_near['mean_p_inside']:.2f} inside and {wedge_near['mean_p_outside']:.2f} outside, so barangays near "
    "the crater rank high in any wind.\n"
    f"- Reports only partly follow the modeled wind: {in_wedge['share_inside_wedge']:.0%} of the "
    f"{in_wedge['barangay_days']} reported barangay-days from 2024 to 2026 were inside its 45-degree wedge, and "
    f"{in_wedge['share_within_45deg']:.0%} within 45 degrees of its direction.\n"
    f"- On report days the plume rose higher than usual. The daily maximum height had a median of "
    f"{heights['report days']['median_of_daily_max_m']:,.0f} m above the crater (up to "
    f"{heights['report days']['highest_daily_max_m']:,.0f} m), against "
    f"{heights['other days']['median_of_daily_max_m']:,.0f} m on other days. Our plume wind is read between 800 and "
    "700 hPa, about 2.0 to 3.2 km above sea level.\n"
    f"- We checked whether higher wind fits ashfall better. Of {upper['ashfall_barangay_days']} ashfall "
    f"barangay-days on {upper['report_days']} report days, {upper_share['800-700hPa']:.0%} were within 45 degrees "
    f"of the 800-700 hPa drift we use, {upper_share['600hPa']:.0%} of the 600 hPa drift (about "
    f"{upper_km['600hPa']:.1f} km) and {upper_share['500hPa']:.0%} of the 500 hPa drift (about "
    f"{upper_km['500hPa']:.1f} km). {upper_verdict}\n"
    "- Near the crater, risk stays raised in every direction because wind shifts during the day and some reported "
    "barangays were upwind. We kept the model unchanged after testing; more recorded events would help it weigh "
    "wind direction more.")
st.caption("Source: our forecast-drivers analysis (notebook 05).")

exposure_model = exposure["scoring_model"]
st.subheader("Eruption response")
st.markdown(
    "The eruption-response map colors the 20 barangays with the highest chance of being reached (p_exposed) dark "
    "red, the next 40 orange and the rest pale yellow. Its list follows the same groups, then puts barangays with "
    "more children under 5 and adults 60+ first within each group, and downwind barangays first if still tied. On "
    f"the five 2026 event days the final exposure model ({exposure_model}) flagged "
    f"{exposure['test'][exposure_model]['recall']:.0%} of the barangays reported exposed, against "
    f"{exposure['test'][f'distance only (N from {exposure_model})']['recall']:.0%} for distance alone flagging the "
    "same number of barangays.")

st.subheader("Columns in the downloads")
st.table(pd.DataFrame([
    ("p_exposed", "Chance of being reached, 0 to 1: if the volcano releases ash or gas, how likely it reaches the "
                  "barangay"),
    ("pct_rise_s40", "Rise in risk (%): expected rise in respiratory consultations for children under 5 and adults "
                     "60+, compared with a normal day"),
    ("extra_all_s40", "Expected extra consultations per day, whole barangay"),
    ("extra_under5_s40, extra_60plus_s40", "Expected extra consultations per day among children under 5, and among "
                                           "adults 60+"),
    ("risk_rank, priority_rank", "Order of the daily-outlook list and of the eruption-response list"),
    ("exposure_rank, exposure_tier", "Rank by p_exposed, and Top 20, Next 40 or Rest from it (the map colors)"),
    ("downwind", "Centroid inside the 45-degree forecast plume wedge on the map"),
], columns=["Column", "Meaning"]), hide_index=True)
st.caption(f"All values use the main scenario: a {health_settings['main_scenario_ugm3']} µg/m³ rise in 24-hour SO2 "
           "for a barangay that is surely exposed on a typical report day.")

st.subheader("Live forecast")
st.markdown(
    f"- The Forecast page runs the saved final models on the latest PHIVOLCS data and the Open-Meteo wind forecast. "
    f"The final SO2 model ({metrics['so2_next_day']['forecast_model']}) forecasts the next day's emission from the "
    "last data date, and Days 2 and 3 reuse that value.\n"
    "- Earthquake counts and plume height stay at their latest values. In notebook 02, the 7-day earthquake mean "
    "and the plume height of a date include that date itself, which a forecast cannot know yet.\n"
    "- Wind at plume height comes from the forecast for each day and sets the plume direction. On replay dates "
    "the plume wedge shows that day's wind at plume height, the direction the exposure model used, and the drift "
    f"card also gives the final drift model's forecast ({metrics['drift_next_day']['forecast_model']}).\n"
    f"- The plume index, the exposure model ({exposure['scoring_model']}) and the health formula "
    f"(q_ref = {health_settings['q_ref_td']:,.0f} t/d, S = {health_settings['main_scenario_ugm3']} µg/m³) are the "
    "same code as notebooks 02 and 03. Given the notebook inputs and the historical wind, this code reproduces "
    "the saved 2026 exposure scores, risk levels and SHAP reasons.")

st.subheader("Data sources")
st.markdown("\n".join(f"- {text} [{url}]({url})" for text, url in SOURCES)
            + "\n- Department of Health. Field Health Services Information System (FHSIS) annual report 2022, "
              "source of the baseline consultation rates."
            + "\n- Sulfur odor and ashfall reports from PHIVOLCS, news and LGU posts, checked by our team.")

st.subheader("Limitations")
st.markdown("\n".join(f"- {item}" for item in limitations(metrics)))
st.markdown("**BantAI Baga supports, but does not replace, PHIVOLCS and DOH decisions.**")
