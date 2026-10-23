"""Forecast: barangay respiratory risk for the next 3 days, laid out as our original dashboard design."""
import streamlit as st

import components as ui
import dashboard_data as dd

live = dd.live_forecast()

with st.container(border=True):
    head = st.columns([3, 2], vertical_alignment="center")
    with head[1]:
        horizon = st.segmented_control("Forecast day", dd.HORIZONS, default=dd.HORIZONS[0], key="horizon",
                                       required=True, persist_state="session", label_visibility="collapsed",
                                       width="stretch", disabled=live is None)
        compare = st.toggle("Compare 3 days", key="compare_days", persist_state="session", disabled=live is None)
    if live is None:
        view = dd.replay_view(dd.DATE_MAX)
        subtitle = f"Showing the latest replay date, {dd.long_date(view['day'])}"
    else:
        view = dd.forecast_view(live, horizon or dd.HORIZONS[0])
        subtitle = dd.view_title(view)
    head[0].html(f'<div class="bb-title">Kanlaon respiratory risk forecast</div>'
                 f'<div class="bb-subtitle">{ui.esc(subtitle)}</div>')
    mode = ui.mode_switch()

if live is None:
    st.warning("The wind forecast from Open-Meteo could not be loaded, so this page shows the latest replay date "
               f"({dd.short_date(dd.DATE_MAX)}) instead of a forecast. Please try again in a few minutes.")
else:
    fetched = live["fetched_at"]
    st.html(f'<div class="bb-dataline">PHIVOLCS data up to {dd.short_date(live["last_data_date"])}. Wind forecast '
            f'from Open-Meteo, fetched {dd.short_date(fetched)}, {fetched:%H:%M} Philippine time.</div>')
    if compare:
        ui.compare_days(live, mode == dd.MODES[1])
        st.divider()

ui.show_day(view, mode == dd.MODES[1], map_key=f"forecast_{view['day']}_{mode}")

if live is not None:
    with st.expander("How this forecast is made"):
        state = live["state"]
        health_settings = dd.load_metrics()["health_impact"]
        st.markdown(
            f"- Next-day SO2 comes from the final model ({view['so2_model']}) applied to the latest PHIVOLCS "
            f"data ({dd.short_date(live['last_data_date'])}). Days 2 and 3 reuse the Day 1 value, "
            f"{live['so2_td']:,.0f} t/d.\n"
            "- Earthquake counts stay at their latest values: the counts of the last three data days and the mean "
            f"of the last seven days. Plume height is {state['plume_height_m']:,.0f} m above the crater, the "
            "latest daily median.\n"
            "- Wind at plume height is the Open-Meteo forecast for each day, averaged from 06:00 to 18:00. It "
            "sets the plume direction, the plume index and the angle of each barangay from the plume.\n"
            "- The exposure model and the health formula are the same code as notebooks 02 and 03, with "
            f"q_ref = {health_settings['q_ref_td']:,.0f} t/d and S = "
            f"{health_settings['main_scenario_ugm3']} µg/m³.")
