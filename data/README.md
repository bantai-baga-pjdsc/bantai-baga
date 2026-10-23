# Data

The notebooks read raw files from `data/raw/` and write their tables to `data/processed/`. Neither folder is in
git: the raw files are large, and the PHIVOLCS terms do not allow redistribution. Two small inputs made by the
authors are in git: `data/report_log/` and `data/reference/`.

## Get the raw data

1. Download the open files. The script saves them in `data/raw/` with the exact names the notebooks expect,
   keeps files that are already there, and prints the manual steps for the rest:

   ```bash
   python scripts/download_open_data.py
   ```

2. Download the PHIVOLCS and SRTM files by hand (steps below and in the script output). Both need a free
   account.
3. Run the notebooks with `python scripts/run_pipeline.py` (see the main [README](../README.md#full-reproduction)).

We checked the script against the files behind our results: the boundaries, wind, census and health facility
files it downloads are byte-identical to ours.

## Raw files

| File in `data/raw/` | Source | Link | License or terms | How to get it | Used by |
|---|---|---|---|---|---|
| `SO2 Kanlaon FlySpec Survey.csv` | PHIVOLCS, Local Active Volcanoes Archive: SO2 flux, FlySpec survey | [wovodat.phivolcs.dost.gov.ph](https://wovodat.phivolcs.dost.gov.ph/data/download) | [PHIVOLCS data policy](https://wovodat.phivolcs.dost.gov.ph/user/policy): free for research, crisis response and education after registration; cite DOST-PHIVOLCS; no redistribution | Manual, free account | 01 |
| `SO2 Kanlaon Mobile DOAS Survey.csv` | PHIVOLCS, Local Active Volcanoes Archive: SO2 flux, mobile DOAS survey | same as above | same as above | Manual, free account | 01 |
| `SO2 Kanlaon Codcod Scan DOAS.csv` | PHIVOLCS, Local Active Volcanoes Archive: SO2 flux, Codcod scanning DOAS station | same as above | same as above | Manual, free account | 01 |
| `Kanlaon Steaming Activity.csv` | PHIVOLCS, Local Active Volcanoes Archive: visual observations (plume intensity, height above the crater, drift) | same as above | same as above | Manual, free account | 01 |
| `Daily Count by Volcano.csv` | PHIVOLCS, Local Active Volcanoes Archive: daily volcanic earthquake counts by class | same as above | same as above | Manual, free account | 01 |
| `wind_kanlaon_hourly.csv` | Open-Meteo Historical Forecast API, hourly wind at 10 m, 800 hPa and 700 hPa over the crater (10.412 N, 123.132 E), Asia/Manila time, m/s | [open-meteo.com](https://open-meteo.com/en/docs/historical-forecast-api) | [CC BY 4.0](https://open-meteo.com/en/licence) | Script | 01, 02, 05 |
| `wind_kanlaon_upper_report_days.csv` | Open-Meteo Historical Forecast API, hourly wind at 800 to 500 hPa on report days | [open-meteo.com](https://open-meteo.com/en/docs/historical-forecast-api) | [CC BY 4.0](https://open-meteo.com/en/licence) | Made by notebook 05 on its first run | 05 |
| `N10E122.SRTMGL1.hgt.zip`, `N10E123.SRTMGL1.hgt.zip` | NASA JPL, SRTM Global 1 arc second, version 3 (keep zipped) | [doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003](https://doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003) | [NASA Earthdata data use guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance): free to use; cite the DOI | Manual, free NASA Earthdata account | 01 |
| `barangays_negros.geojson` | Faeldon, Philippines JSON maps (2023 high-resolution barangay files of Negros Occidental, Negros Oriental and Bacolod City, joined into one file with a `muni_code` column) | [github.com/faeldon/philippines-json-maps](https://github.com/faeldon/philippines-json-maps) | MIT | Script | 01, 04, app build |
| `2020-census-total-popn_single-age_malefemale_admin4.xlsx` | Philippine Statistics Authority, 2020 census population by single-year age, sex and barangay, on the Humanitarian Data Exchange | [data.humdata.org](https://data.humdata.org/dataset/popn-single-year-age-sex-and-barangay-census-2020) | CC BY | Script | 01, 03, 04, app build |
| `hotosm_phl_health_facilities_osm_geojson.zip` | Humanitarian OpenStreetMap Team, Philippines health facilities (OpenStreetMap export, keep zipped) | [data.humdata.org](https://data.humdata.org/dataset/hotosm_phl_health_facilities) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), © OpenStreetMap contributors | Script | 01, 04, app build |
| `ANNUAL_FHSIS_2022.pdf` | Department of Health, Epidemiology Bureau, Field Health Services Information System annual report 2022 | [doh.gov.ph](https://doh.gov.ph/data-publications/fhsis-2022/) | Public government report; no license stated | Manual (the site blocks scripted downloads) | Source of `data/reference/baseline_rates_fhsis2022.csv`; no notebook reads it |

"Used by" lists the notebooks (01 to 05) and `app/build_app_data.py` (app build).
`app/check_forecast_consistency.py` also reads `wind_kanlaon_hourly.csv`.

## Inputs in git

| File | Content | Used by |
|---|---|---|
| `data/report_log/report_log.csv` | Sulfur odor and ashfall reports per barangay and event date, compiled by the authors from PHIVOLCS bulletins, news and local government posts. Each row links its source. | 01, 03, 04, 05, app build |
| `data/reference/baseline_rates_fhsis2022.csv` | Acute respiratory consultation rates per area, taken by the authors from the FHSIS 2022 annual report | 03, app build |

## Snapshots and versions

- PHIVOLCS records: the study period is 2024-01-01 to 2026-10-21. Later downloads include newer days, and
  PHIVOLCS may revise past values.
- Health facilities: we used the HOTOSM snapshot of 2026-10-12. HOTOSM refreshes this export regularly, so a
  later download may hold a few more or fewer facilities and change the response plan slightly.
- Barangay boundaries: the script pins the faeldon repository to one commit, so the file does not change.
- Wind: the script requests 2024-01-01 to 2026-10-20, the last full day in our file.

## Processed tables

The notebooks write these to `data/processed/`:

| File | Made by | Content |
|---|---|---|
| `volcano_daily.csv` | 01 | One row per day: SO2, plume height and drift, earthquake counts, wind at plume height |
| `barangays_study_area.csv` | 01 | Study barangays: centroid, distance and bearing from the crater, elevation, population by age |
| `barangay_daily_panel.csv` | 01 | One row per barangay and day: the exposure model inputs and the report label |
| `next_day_forecasts.csv` | 02 | Next-day SO2 and drift forecasts per day |
| `exposure_scores.csv`, `exposure_shap_top3.csv` | 02 | Exposure probability per barangay-day, and its top 3 SHAP features (2026) |
| `health_impact.csv` | 03 | Expected extra consultations and risk level per barangay-day |
| `health_facility_bases.csv` | 04 | Candidate bases for roving medical teams |
