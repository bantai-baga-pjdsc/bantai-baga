"""Health impact helpers for SO2 exposure.

Extra cases follow dY = P x Y0 x (RR^(dC/10) - 1), with RR per 10 ug/m3 of 24-hour SO2.
"""
import numpy as np
import pandas as pd

RR_PER_10_UGM3 = 1.0126  # Carlsen et al. (2021)
WHO_SO2_24H_UGM3 = 40

RISK_LEVELS = ["Low", "Moderate", "High", "Very high"]
RISK_BINS_UGM3 = [0, 5, 20, 40, np.inf]


def activity_factor(so2_td, q_ref_td, cap):
    """SO2 emission relative to a reference emission, capped from above."""
    return np.minimum(np.asarray(so2_td, dtype=float) / q_ref_td, cap)


def relative_increase(delta_c_ugm3, rr=RR_PER_10_UGM3):
    """Fractional rise in cases for an SO2 increase: RR^(dC/10) - 1."""
    return np.power(rr, np.asarray(delta_c_ugm3, dtype=float) / 10) - 1


def extra_cases(pop, rate_per_day, delta_c_ugm3, rr=RR_PER_10_UGM3):
    """Expected extra cases per day: P x Y0 x (RR^(dC/10) - 1); Y0 is a scalar or one rate per row."""
    return (np.asarray(pop, dtype=float) * np.asarray(rate_per_day, dtype=float)
            * relative_increase(delta_c_ugm3, rr))


def risk_level(delta_c_ugm3):
    """Risk level from the SO2 increase: Low < 5, Moderate < 20, High < 40, Very high >= 40 ug/m3."""
    return pd.cut(delta_c_ugm3, RISK_BINS_UGM3, right=False, labels=RISK_LEVELS)
