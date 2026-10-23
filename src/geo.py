"""Geographic and wind helpers for BantAI Baga.

Conventions
- Wind direction is where the wind comes FROM (meteorological).
- Plume drift is where the plume moves TOWARD = wind direction + 180.
- u is the eastward component, v is the northward component (m/s).
"""
import numpy as np

CRATER_LAT = 10.412
CRATER_LON = 123.132
CRATER_ELEV_M = 2435
EARTH_RADIUS_KM = 6371.0088

SECTORS_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
SECTOR_DEG = {name: i * 45.0 for i, name in enumerate(SECTORS_8)}

# 16-point compass labels used in the PHIVOLCS steaming bulletins
COMPASS_16_DEG = {
    "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
    "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
}

# Free-text drift labels, mapped by meaning to a compass direction
DRIFT_TEXT_DEG = {
    "general north": 0.0,
    "general east": 90.0,
    "general south": 180.0,
    "general west": 270.0,
    "west": 270.0,
    "N-NE": 22.5,             # same as NNE
    "S-SW": 202.5,            # same as SSW
    "southwest to west": 247.5,  # same as WSW
    "NW to W": 292.5,         # same as WNW
    "NW/SW": 270.0,           # midpoint of NW (315) and SW (225)
}


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def destination_point(lat, lon, bearing, dist_km):
    """Latitude and longitude reached from a point after dist_km along an initial bearing (degrees)."""
    lat1, lon1, theta = map(np.radians, (lat, lon, bearing))
    delta = np.asarray(dist_km, dtype=float) / EARTH_RADIUS_KM
    lat2 = np.arcsin(np.sin(lat1) * np.cos(delta) + np.cos(lat1) * np.sin(delta) * np.cos(theta))
    lon2 = lon1 + np.arctan2(np.sin(theta) * np.sin(delta) * np.cos(lat1), np.cos(delta) - np.sin(lat1) * np.sin(lat2))
    return np.degrees(lat2), np.degrees(lon2)


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees clockwise from north (0 to 360)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    x = np.sin(lon2 - lon1) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(lon2 - lon1)
    return (np.degrees(np.arctan2(x, y)) + 360) % 360


def wind_to_uv(speed, direction_from_deg):
    """Speed and FROM-direction to u (east) and v (north) components."""
    rad = np.radians(direction_from_deg)
    return -speed * np.sin(rad), -speed * np.cos(rad)


def uv_to_wind(u, v):
    """u and v components to speed and FROM-direction (0 to 360)."""
    speed = np.hypot(u, v)
    direction_from = (np.degrees(np.arctan2(-u, -v)) + 360) % 360
    return speed, direction_from


def interp_by_height(z_target, z_low, z_high, value_low, value_high):
    """Linear interpolation between two levels by height.

    z_target is clipped to [z_low, z_high], so there is no extrapolation.
    Returns the interpolated value and the weight on the upper level (0 to 1).
    """
    w = np.clip((z_target - z_low) / (z_high - z_low), 0, 1)
    return value_low + w * (value_high - value_low), w


def daily_plume_wind(wind_hours, plume_alt_m):
    """Daily plume-level wind from hourly 800/700 hPa wind at a given plume altitude per date.

    wind_hours: hourly rows with a "date" column and the Open-Meteo 800/700 hPa columns.
    plume_alt_m: Series of plume altitude (m above sea level) indexed by date.
    Returns wind_dir_plume (FROM), wind_speed_plume (mean hourly speed) and wind_drift_deg (TOWARD).
    """
    w = wind_hours.copy()
    w["plume_alt_m"] = w["date"].map(plume_alt_m)
    u800, v800 = wind_to_uv(w["wind_speed_800hPa"], w["wind_direction_800hPa"])
    u700, v700 = wind_to_uv(w["wind_speed_700hPa"], w["wind_direction_700hPa"])
    z800, z700 = w["geopotential_height_800hPa"], w["geopotential_height_700hPa"]
    w["u"], _ = interp_by_height(w["plume_alt_m"], z800, z700, u800, u700)
    w["v"], _ = interp_by_height(w["plume_alt_m"], z800, z700, v800, v700)
    w["speed"] = np.hypot(w["u"], w["v"])
    g = w.groupby("date")
    speed, direction_from = g["speed"].mean(), uv_to_wind(g["u"].mean(), g["v"].mean())[1]
    return (speed.to_frame("wind_speed_plume")
            .assign(wind_dir_plume=direction_from, wind_drift_deg=(direction_from + 180) % 360))


def drift_label_to_deg(label):
    """Raw drift label to degrees (direction the plume moves toward). NaN if unknown."""
    if not isinstance(label, str):
        return np.nan
    label = label.strip()
    if label in COMPASS_16_DEG:
        return COMPASS_16_DEG[label]
    return DRIFT_TEXT_DEG.get(label, np.nan)


def deg_to_sector(deg):
    """Degrees to one of 8 sectors (N, NE, ..., NW).

    Each sector spans 45 degrees centered on its direction. A value exactly on a
    boundary (for example WSW = 247.5) goes to the next sector clockwise (W).
    Works on scalars and arrays; NaN gives None.
    """
    deg = np.asarray(deg, dtype=float)
    idx = np.floor(((np.nan_to_num(deg) % 360) + 22.5) / 45).astype(int) % 8
    out = np.where(np.isnan(deg), None, np.array(SECTORS_8, dtype=object)[idx])
    return out.item() if out.ndim == 0 else out


def angle_diff_deg(a, b):
    """Smallest absolute difference between two directions (0 to 180)."""
    return np.abs((np.asarray(a) - np.asarray(b) + 180) % 360 - 180)
