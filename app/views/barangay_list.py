"""Barangay list: all 216 study barangays in priority order for the day on screen."""
import streamlit as st

import components as ui
import dashboard_data as dd

view = dd.focus_view()
st.html('<div class="bb-title">Barangay list</div><div class="bb-subtitle">All 216 study barangays in priority '
        'order</div>')
ui.focus_banner(view)

with st.container(border=True):
    cols = st.columns([3, 2], vertical_alignment="bottom")
    with cols[0]:
        mode = ui.mode_switch()
    search = cols[1].text_input("Find a barangay or municipality", key="list_search", placeholder="Type a name")
eruption = mode == dd.MODES[1]

rows = ui.ranked(view["rows"], eruption).copy()
rows["rank"] = rows["priority_rank"] if eruption else rows["risk_rank"]
rows["reported_that_day"] = rows["psgc_code"].isin(view["reported"])
rows["risk_level"] = rows["risk_level"].astype(str)
st.html(f'<div class="bb-sortline">{ui.esc(ui.SORT_LINES[mode])}</div>')

# the screen shows plain columns; the download keeps every technical column
screen = rows.assign(chance_pct=rows["p_exposed"] * 100, wind=rows["downwind"].map({True: "Downwind", False: ""}))
screen_columns = ["rank", "name", "municipality_name", "exposure_tier" if eruption else "risk_level", "wind",
                  "chance_pct", "pct_rise_s40", "pop_under5", "pop_60plus", "dist_km", "nearest_facility_text"]
if view["source"] == "replay":
    screen_columns.append("reported_that_day")
screen = screen[screen_columns]
if search.strip():
    needle = search.strip().lower()
    screen = screen[screen["name"].str.lower().str.contains(needle, regex=False)
                    | screen["municipality_name"].str.lower().str.contains(needle, regex=False)]
    st.caption(f"{len(screen)} of {len(rows)} barangays match.")


def color_levels(value):
    """Cell style for risk levels and eruption-response tiers, in the map colors."""
    color = {**ui.RISK_COLORS, **ui.TIER_COLORS}.get(value)
    if color is None:
        return ""
    text = "#ffffff" if color in ui.DARK_FILLS else ui.INK
    return f"background-color: {color}; color: {text}"


styled = screen.style.map(color_levels, subset=[c for c in ["risk_level", "exposure_tier"] if c in screen])
st.dataframe(
    styled, hide_index=True, width="stretch", height=620,
    column_config={
        "rank": st.column_config.NumberColumn("Rank", width=60, pinned=True),
        "name": st.column_config.TextColumn("Barangay", width=140, pinned=True),
        "municipality_name": st.column_config.TextColumn("Municipality", width=170),
        "risk_level": st.column_config.TextColumn("Risk level", width=95),
        "exposure_tier": st.column_config.TextColumn("Priority", width=85),
        "wind": st.column_config.TextColumn("Wind", width=85),
        "chance_pct": st.column_config.NumberColumn(ui.CHANCE_LABEL, help=ui.CHANCE_HELP, format="%.0f%%", width=180),
        "pct_rise_s40": st.column_config.NumberColumn(ui.RISE_LABEL, help=ui.RISE_HELP, format="+%.1f%%", width=105),
        "pop_under5": st.column_config.NumberColumn("Children under 5", format="localized", width=135),
        "pop_60plus": st.column_config.NumberColumn("Adults 60+", format="localized", width=95),
        "dist_km": st.column_config.NumberColumn("Distance from crater (km)", format="%.1f", width=190),
        "nearest_facility_text": st.column_config.TextColumn("Nearest health facility", width=320),
        "reported_that_day": st.column_config.CheckboxColumn("Reported that day", width=140),
    })

download_columns = {
    "rank": "rank", "psgc_code": "psgc_code", "name": "barangay", "municipality_name": "municipality",
    "province": "province", "risk_level": "risk_level", "risk_rank": "risk_rank", "priority_rank": "priority_rank",
    "exposure_rank": "exposure_rank", "exposure_tier": "exposure_tier", "downwind": "downwind",
    "p_exposed": "p_exposed", "pct_rise_s40": "pct_rise_s40", "extra_under5_s40": "extra_under5_s40",
    "extra_60plus_s40": "extra_60plus_s40", "extra_under5_60plus": "extra_under5_60plus_s40",
    "extra_all_s40": "extra_all_s40", "pop_total": "pop_total", "pop_under5": "pop_under5", "pop_60plus": "pop_60plus",
    "dist_km": "dist_km", "nearest_facility_name": "nearest_facility", "nearest_facility_type": "nearest_facility_type",
    "nearest_facility_km": "nearest_facility_km"}
if view["source"] == "replay":
    download_columns["reported_that_day"] = "reported_that_day"
download = rows[list(download_columns)].rename(columns=download_columns)
mode_tag = "eruption_response_" if eruption else ""
st.download_button("Download all 216 barangays (CSV)", download.to_csv(index=False).encode("utf-8"),
                   file_name=f"barangay_list_{mode_tag}{view['day']}.csv", mime="text/csv")
st.caption("The download keeps the technical columns; Methods & results explains each one.")
