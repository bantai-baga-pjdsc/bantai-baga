"""Download the open raw data into data/raw with the file names the notebooks expect.

Downloads barangay boundaries, hourly wind, the 2020 census and OpenStreetMap health facilities, then prints the
manual steps for files that need a browser and an account (PHIVOLCS, NASA Earthdata) and lists what is missing.
Existing files are kept unless --force is given. Run from the repository root:
    python scripts/download_open_data.py
"""
import argparse
import json
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_S = 300

# Barangay boundaries: Faeldon, Philippines JSON maps, 2023 high-resolution files, pinned to one commit
FAELDON = ("https://raw.githubusercontent.com/faeldon/philippines-json-maps/"
           "8eeead560246863c8c820c31ca6fbca81a279477/2023/geojson")
PROVINCES_PSGC = [604500000, 704600000]  # Negros Occidental, Negros Oriental
CITIES_PSGC = [630200000]  # Bacolod City, a highly urbanized city outside the provinces

# Hourly wind at the Kanlaon crater; plume drift is the wind direction + 180
OPEN_METEO = "https://historical-forecast-api.open-meteo.com/v1/forecast"
CRATER_LAT, CRATER_LON = 10.412, 123.132
WIND_COLUMNS = ["wind_speed_10m", "wind_direction_10m", "wind_speed_800hPa", "wind_direction_800hPa",
                "wind_speed_700hPa", "wind_direction_700hPa", "geopotential_height_800hPa",
                "geopotential_height_700hPa"]
WIND_START, WIND_END = "2024-01-01", "2026-10-20"

HDX_API = "https://data.humdata.org/api/3/action/package_show"
HDX_FILES = {
    "2020-census-total-popn_single-age_malefemale_admin4.xlsx": "popn-single-year-age-sex-and-barangay-census-2020",
    "hotosm_phl_health_facilities_osm_geojson.zip": "hotosm_phl_health_facilities",
}

MANUAL_FILES = {
    "SO2 Kanlaon FlySpec Survey.csv": "phivolcs",
    "SO2 Kanlaon Mobile DOAS Survey.csv": "phivolcs",
    "SO2 Kanlaon Codcod Scan DOAS.csv": "phivolcs",
    "Kanlaon Steaming Activity.csv": "phivolcs",
    "Daily Count by Volcano.csv": "phivolcs",
    "N10E122.SRTMGL1.hgt.zip": "srtm",
    "N10E123.SRTMGL1.hgt.zip": "srtm",
}
MANUAL_STEPS = {
    "phivolcs": """PHIVOLCS Local Active Volcanoes Archive (free account needed; PHIVOLCS does not allow redistribution)
  1. Register and sign in at https://wovodat.phivolcs.dost.gov.ph
  2. Open Monitoring Data (https://wovodat.phivolcs.dost.gov.ph/data/download).
  3. Download these Kanlaon records as CSV, from 2024-01-01 to the latest date, and save them in data/raw
     with exactly these names:
       SO2 flux, FlySpec survey          -> SO2 Kanlaon FlySpec Survey.csv
       SO2 flux, Mobile DOAS survey      -> SO2 Kanlaon Mobile DOAS Survey.csv
       SO2 flux, Codcod scanning DOAS    -> SO2 Kanlaon Codcod Scan DOAS.csv
       Visual observation, steaming      -> Kanlaon Steaming Activity.csv
       Daily volcanic earthquake counts  -> Daily Count by Volcano.csv""",
    "srtm": """NASA SRTM 1 arc-second elevation, version 3 (free NASA Earthdata account needed)
  1. Register at https://urs.earthdata.nasa.gov
  2. Sign in and download these two tiles into data/raw without unzipping them:
       https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1.003/N10E122.SRTMGL1.hgt/N10E122.SRTMGL1.hgt.zip
       https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1.003/N10E123.SRTMGL1.hgt/N10E123.SRTMGL1.hgt.zip""",
}


def get_json(url, **params):
    """GET a URL and parse the JSON response."""
    response = requests.get(url, params=params, timeout=TIMEOUT_S)
    response.raise_for_status()
    return response.json()


def download_boundaries(path):
    """Barangay polygons of Negros Occidental, Negros Oriental and Bacolod City in one GeoJSON file."""
    municipalities = []
    for province in PROVINCES_PSGC:
        listing = get_json(f"{FAELDON}/provdists/hires/municities-provdist-{province}.0.1.json")
        municipalities += sorted(f["properties"]["adm3_psgc"] for f in listing["features"])
    features = []
    for adm3 in municipalities + CITIES_PSGC:
        for feature in get_json(f"{FAELDON}/municities/hires/bgysubmuns-municity-{adm3}.0.1.json")["features"]:
            feature["properties"]["muni_code"] = str(feature["properties"]["adm3_psgc"])
            features.append(feature)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    print(f"  {len(features):,} barangays from {len(municipalities) + len(CITIES_PSGC)} municipalities and cities")


def download_wind(path):
    """Hourly wind at 10 m, 800 hPa and 700 hPa over the crater, Asia/Manila time, m/s."""
    hourly = get_json(OPEN_METEO, latitude=CRATER_LAT, longitude=CRATER_LON, start_date=WIND_START,
                      end_date=WIND_END, hourly=",".join(WIND_COLUMNS), wind_speed_unit="ms",
                      timezone="Asia/Manila")["hourly"]
    wind = pd.DataFrame(hourly)[["time", *WIND_COLUMNS]]
    wind.to_csv(path, index=False, lineterminator="\n")
    print(f"  {len(wind):,} hours, {wind['time'].iloc[0]} to {wind['time'].iloc[-1]}")


def download_hdx(path):
    """A file from the Humanitarian Data Exchange, found by its name in the dataset's resource list."""
    resources = get_json(HDX_API, id=HDX_FILES[path.name])["result"]["resources"]
    url = next((r["url"] for r in resources if r["url"].lower().endswith(path.name.lower())), None)
    if url is None:
        raise RuntimeError(f"{path.name} is no longer listed on HDX dataset {HDX_FILES[path.name]}")
    with requests.get(url, stream=True, timeout=TIMEOUT_S) as response:
        response.raise_for_status()
        with path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1 << 20):
                file.write(chunk)
    print(f"  {path.stat().st_size / 1e6:.1f} MB from {url}")


DOWNLOADS = {
    "barangays_negros.geojson": download_boundaries,
    "wind_kanlaon_hourly.csv": download_wind,
    **{name: download_hdx for name in HDX_FILES},
}


def main():
    """Download the open files that are missing, then list the manual downloads still needed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "raw", help="folder to save into")
    parser.add_argument("--force", action="store_true", help="download again even if a file exists")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    failed = []
    for name, download in DOWNLOADS.items():
        path = args.out / name
        if path.exists() and not args.force:
            print(f"{name}: already there, kept")
            continue
        print(f"{name}: downloading")
        try:
            download(path)
        except (requests.RequestException, RuntimeError, KeyError) as error:
            path.unlink(missing_ok=True)
            failed.append(name)
            print(f"  failed: {error}")

    missing = [name for name in MANUAL_FILES if not (args.out / name).exists()]
    for source in dict.fromkeys(MANUAL_FILES[name] for name in missing):
        print(f"\nManual download: {MANUAL_STEPS[source]}")

    print(f"\nWritten to {args.out}")
    print("Notebook 05 downloads wind_kanlaon_upper_report_days.csv itself on its first run.")
    if failed or missing:
        raise SystemExit(f"Still missing: {', '.join(failed + missing)}")
    print("All raw files are in place.")


if __name__ == "__main__":
    main()
