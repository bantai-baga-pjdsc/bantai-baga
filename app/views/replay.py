"""Replay past events: saved model outputs for any date from 2024 to 2026."""
from datetime import date

import pandas as pd
import streamlit as st

import components as ui
import dashboard_data as dd

QUICK_PICKS = [("2026-02-19: largest 2026 event, out-of-sample", date(2026, 2, 19)),
               ("2024-09-11: highest SO2, in-sample", date(2024, 9, 11))]

if "replay_day" not in st.session_state:
    st.session_state["replay_day"] = QUICK_PICKS[0][1]


def pick_day(day):
    """Quick-pick callback for the date picker."""
    st.session_state["replay_day"] = day


with st.container(border=True):
    head = st.columns([3, 2], vertical_alignment="top")
    with head[1]:
        st.date_input("Date", min_value=dd.DATE_MIN, max_value=dd.DATE_MAX, key="replay_day",
                      persist_state="session")
        for label, quick_day in QUICK_PICKS:
            st.button(label, on_click=pick_day, args=(quick_day,), width="stretch")
    day = st.session_state["replay_day"]
    with head[0]:
        st.html('<div class="bb-title">Replay past events</div>'
                f'<div class="bb-subtitle">{ui.esc(dd.long_date(day))}</div>')
        mode = ui.mode_switch()
        reports = dd.load_reported()
        if reports.loc[reports["date"] == pd.Timestamp(day), "ashfall"].any():
            st.html('<div class="bb-sortline"><b>Ashfall was reported on this date.</b> Eruption response shows where '
                    'exposure was most likely.</div>')

if day < dd.TEST_START:
    note = ("2024-2025 dates were used for training, so their maps are in-sample. SHAP reasons are available for "
            "2026 dates only.")
else:
    note = "2026 dates were not used for training, tuning or thresholds, so their maps are out-of-sample."
st.html(f'<div class="bb-dataline">{note}</div>')

ui.show_day(dd.replay_view(day), mode == dd.MODES[1], map_key=f"replay_{day}_{mode}")
