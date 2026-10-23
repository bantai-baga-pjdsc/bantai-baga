"""Gaussian plume index for barangays around Kanlaon.

Steady-state Gaussian plume with ground reflection, receptor at ground level:
    C = Q / (pi * u * sigma_y * sigma_z) * exp(-y^2 / (2 sigma_y^2)) * exp(-H^2 / (2 sigma_z^2))
Dispersion: Briggs (1973) open-country (rural) curves, Pasquill-Gifford stability class D.
The source is a point at the crater; x is the downwind and y the crosswind distance (m).
"""
import numpy as np

from src.geo import CRATER_ELEV_M

MIN_WIND_SPEED_MS = 1.0
MIN_EFFECTIVE_HEIGHT_M = 10.0


def tonnes_per_day_to_g_per_s(q_td):
    """Emission rate from t/d to g/s."""
    return np.asarray(q_td, dtype=float) * 1e6 / 86400


def briggs_rural_d_sigmas(x_m):
    """Briggs rural class D sigma_y and sigma_z (m) at downwind distance x (m)."""
    x_m = np.asarray(x_m, dtype=float)
    sigma_y = 0.08 * x_m / np.sqrt(1 + 0.0001 * x_m)
    sigma_z = 0.06 * x_m / np.sqrt(1 + 0.0015 * x_m)
    return sigma_y, sigma_z


def downwind_crosswind_m(dist_km, angle_diff_deg):
    """Downwind x and crosswind y (m) from distance to the crater and angle off the drift axis."""
    rad = np.radians(np.asarray(angle_diff_deg, dtype=float))
    dist_m = np.asarray(dist_km, dtype=float) * 1000
    return dist_m * np.cos(rad), dist_m * np.sin(rad)


def effective_height_flat_m(plume_height_m, elev_m):
    """Plume height above the receptor on flat terrain: crater altitude + plume height - receptor elevation."""
    h = CRATER_ELEV_M + np.asarray(plume_height_m, dtype=float) - np.asarray(elev_m, dtype=float)
    return np.maximum(h, MIN_EFFECTIVE_HEIGHT_M)


def effective_height_terrain_m(plume_height_m):
    """Plume height above the receptor when the plume follows the slope: plume height above the crater."""
    return np.maximum(np.asarray(plume_height_m, dtype=float), MIN_EFFECTIVE_HEIGHT_M)


def gaussian_plume_ugm3(q_gs, u_ms, h_m, x_m, y_m):
    """Ground-level concentration (ug/m3) at (x, y); zero upwind (x <= 0)."""
    q_gs, u_ms, h_m, x_m, y_m = (np.asarray(a, dtype=float) for a in (q_gs, u_ms, h_m, x_m, y_m))
    u_ms = np.maximum(u_ms, MIN_WIND_SPEED_MS)
    downwind = x_m > 0
    sigma_y, sigma_z = briggs_rural_d_sigmas(np.where(downwind, x_m, 1.0))
    c = (q_gs / (np.pi * u_ms * sigma_y * sigma_z)
         * np.exp(-y_m ** 2 / (2 * sigma_y ** 2))
         * np.exp(-h_m ** 2 / (2 * sigma_z ** 2)))
    return np.where(downwind, c * 1e6, 0.0)


def compute_plume_index(q_td, wind_speed_ms, plume_height_m, elev_m, dist_km, angle_diff_deg, terrain="following"):
    """Plume index per barangay-day; terrain is "following" (H = plume height) or "flat"."""
    x_m, y_m = downwind_crosswind_m(dist_km, angle_diff_deg)
    if terrain == "following":
        h_m = effective_height_terrain_m(plume_height_m)
    elif terrain == "flat":
        h_m = effective_height_flat_m(plume_height_m, elev_m)
    else:
        raise ValueError(f"unknown terrain option: {terrain}")
    return gaussian_plume_ugm3(tonnes_per_day_to_g_per_s(q_td), wind_speed_ms, h_m, x_m, y_m)
