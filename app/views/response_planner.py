"""Response planner: roving teams, masks and nebulizer kits for the day on screen."""
import numpy as np
import streamlit as st

import components as ui
import dashboard_data as dd
import risk_map
from src import allocation

view = dd.focus_view()
st.html('<div class="bb-title">Response planner</div><div class="bb-subtitle">Maximum coverage plan for roving '
        'medical teams, masks and nebulizer kits</div>')
ui.focus_banner(view)

with st.container(border=True):
    eruption = ui.mode_switch() == dd.MODES[1]
    cols = st.columns(4)
    k_teams = cols[0].slider("Roving medical teams", 1, 10, 5, key="plan_teams", persist_state="session")
    max_km = cols[1].slider("Travel limit (km by road)", 5, 20, 10, key="plan_max_km", persist_state="session")
    masks = cols[2].slider("Masks", 0, 300_000, allocation.SCENARIO_MASKS, step=5_000, key="plan_masks",
                           persist_state="session")
    kits = cols[3].slider("Nebulizer kits", 0, 1_000, allocation.SCENARIO_KITS, key="plan_kits",
                          persist_state="session")
    bases = dd.load_bases()
    base_names = dict(zip(bases["base_id"], bases["label"] + " (" + bases["amenity"].str.replace("_", " ")
                          + ", " + bases["dist_crater_km"].map("{:.1f}".format) + " km from the crater)"))
    unavailable = st.multiselect("Unavailable facilities (left out of the plan)",
                                 sorted(base_names, key=base_names.get), format_func=base_names.get,
                                 key="plan_unavailable", persist_state="session",
                                 placeholder="All candidate facilities are available")
    st.caption(f"Default supplies are a scenario based on the DOH response to the December 2024 eruption "
               f"({allocation.SCENARIO_MASKS:,} masks and {allocation.SCENARIO_KITS} nebulizer kits; Bayoran, "
               f"2025), not a count of current stock. Road distance is {allocation.ROAD_FACTOR} x the "
               "straight-line distance, a rough allowance for winding roads.")

unavailable = tuple(sorted(unavailable))
available = len(bases) - len(unavailable)
n_out = dd.barangays_out_of_reach(max_km, unavailable)
st.markdown(f"At a {max_km} km travel limit, **{n_out} of {dd.N_BARANGAYS} barangays** are beyond reach of all "
            f"{available} available candidate facilities, so no plan can cover them.")

try:
    plan = dd.response_plan(dd.plan_day_rows(view), k_teams, max_km, masks, kits, unavailable)
except (ValueError, RuntimeError) as err:
    st.error(f"No plan could be made with these settings: {err}")
    st.stop()

rows = view["rows"]
plan_rows = plan["barangays"].merge(rows[["psgc_code", "name", "municipality_name", "risk_level", "downwind"]],
                                    on="psgc_code", how="left", validate="1:1")
plan_bases = plan["bases"]
covered = plan_rows["covered"]
ui.metric_cards([
    ("Barangays covered by a team", f"{int(covered.sum())} of {dd.N_BARANGAYS}",
     f"Within {max_km} km by road of a team base"),
    ("Under 5 and 60+ residents covered",
     f"{int(plan_rows.loc[covered, ['pop_under5', 'pop_60plus']].sum().sum()):,}",
     "Children under 5 and adults 60 and over in covered barangays"),
    ("Masks allocated", f"{int(plan_rows['masks'].sum()):,}",
     "Each barangay gets at most its need (residents x chance of being reached), so some may be left over"),
    ("Nebulizer kits at team bases", f"{int(plan_bases['kits'].sum()):,}",
     "Split by the extra consultations expected at each base"),
])

base_label = bases.set_index("base_id")["label"]
plan_rows["team_base"] = plan_rows["nearest_base_id"].map(base_label).where(covered, "")
coverage = np.where(covered, "covered by " + plan_rows["team_base"], "outside team reach")
map_table = ui.map_rows(rows, eruption)
map_table["tooltip"] = (map_table["tooltip"] + "<br>"
                        + map_table["psgc_code"].map(dict(zip(plan_rows["psgc_code"], coverage))).map(ui.esc) + ", "
                        + map_table["psgc_code"].map(dict(zip(plan_rows["psgc_code"], plan_rows["masks"])))
                        .map("{:,} masks".format))
candidates = bases[~bases["base_id"].isin(unavailable)].copy()
kits_by_base = plan_bases.set_index("base_id")
candidates["tooltip"] = [
    f"{label}: team base, {kits_by_base.loc[b, 'kits']} kits, {kits_by_base.loc[b, 'barangays_assigned']} barangays"
    if b in kits_by_base.index else label for b, label in zip(candidates["base_id"], candidates["label"])]
reach_km = max_km / allocation.ROAD_FACTOR
m = risk_map.make_map(dd.load_polygons(), map_table, plume_deg=view["drift_deg"], reported=view["reported"],
                      faded=frozenset(plan_rows.loc[~covered, "psgc_code"]),
                      team_bases=(candidates, list(plan_bases["base_id"]), reach_km))
st.html(f'<div class="bb-maptitle">{ui.esc(ui.plume_title(view))}</div>')
ui.show_map(m, key=f"plan_{view['day']}_{eruption}_{k_teams}_{max_km}_{masks}_{kits}_{len(unavailable)}")
ui.legend(eruption, plume=view["drift_deg"] is not None, reported=bool(view["reported"]), extra=[
    ("Team base", f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;'
                  f'background:{risk_map.BASE_COLOR};border:2px solid #fff;box-shadow:0 0 0 1px #999"></span>'),
    (f"Team reach ({max_km} km by road)", f'<span style="display:inline-block;width:22px;border-top:1.5px dashed '
                                          f'{risk_map.BASE_COLOR}"></span>'),
    ("Other candidate facility", '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                                 'background:#57534e"></span>'),
    ("Faded: outside team reach", '<span class="bb-swatch" style="background:rgba(242,140,40,0.3)"></span>'),
])

st.subheader("Nebulizer kits per team base")
st.caption("Each covered barangay is assigned to its nearest open base; kits are split by the extra "
           "consultations expected at each base.")
bases_table = (plan_bases[["label", "amenity", "dist_crater_km", "barangays_in_reach", "barangays_assigned",
                           "vulnerable_assigned", "kits"]]
               .sort_values("kits", ascending=False)
               .rename(columns={"label": "team_base", "amenity": "type", "vulnerable_assigned":
                                "under5_60plus_assigned"}))
st.dataframe(
    bases_table, hide_index=True, width="stretch",
    column_config={"team_base": "Team base", "type": "Type",
                   "dist_crater_km": st.column_config.NumberColumn("From crater (km)", format="%.1f"),
                   "barangays_in_reach": "Barangays in reach", "barangays_assigned": "Barangays assigned",
                   "under5_60plus_assigned": st.column_config.NumberColumn("Under 5 and 60+ assigned",
                                                                           format="localized"),
                   "kits": "Kits"})

st.subheader("Masks per barangay")
st.caption("Masks are sized by how many residents are likely reached, so large barangays may receive more. "
           "Masks go first to barangays where the most extra consultations are expected per resident, up to each "
           "barangay's need (residents x chance of being reached). Barangays outside team reach still get masks, "
           "which can travel through municipal health offices.")
plan_rows["road_km"] = plan_rows["nearest_base_road_km"].where(covered)
plan_rows["kits_at_base"] = plan_rows["nearest_base_id"].map(kits_by_base["kits"]).where(covered)
plan_rows["wind"] = plan_rows["downwind"].map({True: "Downwind", False: ""})
masks_table = (plan_rows[["psgc_code", "name", "municipality_name", "risk_level", "wind", "covered", "team_base",
                          "road_km", "kits_at_base", "mask_need", "masks"]]
               .rename(columns={"name": "barangay", "municipality_name": "municipality"})
               .sort_values(["masks", "barangay"], ascending=[False, True]))
masks_table["risk_level"] = masks_table["risk_level"].astype(str)
masks_table["mask_need"] = np.floor(masks_table["mask_need"]).astype(int)
st.dataframe(
    masks_table, hide_index=True, width="stretch", height=420,
    column_config={"psgc_code": st.column_config.NumberColumn("PSGC", format="%d"),
                   "barangay": "Barangay", "municipality": "Municipality", "risk_level": "Risk level",
                   "wind": "Wind", "covered": "Covered by a team", "team_base": "Team base",
                   "road_km": st.column_config.NumberColumn("Road km to base", format="%.1f"),
                   "kits_at_base": st.column_config.NumberColumn("Kits at that base", format="%d"),
                   "mask_need": st.column_config.NumberColumn("Mask need", format="localized"),
                   "masks": st.column_config.NumberColumn("Masks", format="localized")})
downloads = st.columns(2)
downloads[0].download_button("Download plan per barangay (CSV)", masks_table.to_csv(index=False).encode("utf-8"),
                             file_name=f"response_plan_barangays_{view['day']}.csv", mime="text/csv",
                             width="stretch")
downloads[1].download_button("Download team bases (CSV)", bases_table.to_csv(index=False).encode("utf-8"),
                             file_name=f"response_plan_team_bases_{view['day']}.csv", mime="text/csv",
                             width="stretch")
