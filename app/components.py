"""Layout pieces shared by the dashboard pages: style, cards, badges, the risk map block and advisories."""
import html

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import dashboard_data as dd
import risk_map
from src import allocation, health

# Warm risk scale, used for map fills and badges alike; eruption-response tiers reuse it
RISK_COLORS = dict(zip(health.RISK_LEVELS, ["#fbe3a0", "#f28c28", "#d7301f", "#7f0000"]))
TIER_COLORS = {"Top 20": RISK_COLORS["Very high"], "Next 40": RISK_COLORS["Moderate"], "Rest": RISK_COLORS["Low"]}
DARK_FILLS = {RISK_COLORS["High"], RISK_COLORS["Very high"]}
INK, MUTED_INK = "#1c1917", "#57534e"
MAP_HEIGHT = 560
DAY_MAP_HEIGHT = 700
COMPARE_MAP_HEIGHT = 380
LANGUAGES = ["English", "Hiligaynon", "Cebuano"]
TOP_COUNT = 10
CARD_SEPARATOR = "\n\n" + "-" * 32 + "\n\n"  # between advisories in the .txt download
# App-generated line on the Low card, above the municipalities that also have barangays on a higher card. It is not
# in advisory_templates.csv; the Hiligaynon and Cebuano lines have been reviewed.
LOW_OTHERS_LABEL = {"English": "All other barangays in:", "Hiligaynon": "Ang tanan nga iban nga barangay sa:",
                    "Cebuano": "Ang tanang ubang barangay sa:"}
CHANCE_LABEL = "Chance of being reached"
CHANCE_HELP = "If the volcano releases ash or gas, how likely it reaches this barangay."
RISE_LABEL = "Rise in risk"
RISE_HELP = ("Expected rise in respiratory consultations for children under 5 and adults 60+, compared with a "
             "normal day.")
SORT_LINES = {
    "Daily outlook": "Sorted by risk level, then by how many young children and older adults could be affected. "
                     "Downwind barangays come first within each risk level.",
    "Eruption response": "Sorted by chance of being reached, then by number of young children and older adults.",
}
MAP_CAPTION = ("Barangays near the crater can be at risk in any wind. Downwind barangays are most likely to be "
               "reached.")

MODE_LINES = {
    "Daily outlook": "Risk levels from the SO2 forecast and the wind at plume height.",
    "Eruption response": "Use when PHIVOLCS has reported an eruption. Ranks barangays by where exposure is most "
                         "likely now.",
}

STYLE = """
<style>
.block-container {padding-top: 3.8rem; padding-bottom: 3rem; max-width: 1440px;}
h1, h2, h3 {letter-spacing: -0.01em; color: #123554;}
[data-testid="stSidebarContent"] {padding-top: 0.4rem;}
.bb-tagline {font-size: 0.88rem; color: #57534e; line-height: 1.35; margin-bottom: 0.4rem;}
.bb-footnote {font-size: 0.8rem; color: #57534e; line-height: 1.35; border-top: 1px solid #e7e5e4;
    padding-top: 0.75rem; margin-top: 0.75rem;}
.bb-title {font-size: 1.55rem; font-weight: 700; color: #123554; line-height: 1.2; margin: 0;}
.bb-subtitle {font-size: 0.98rem; color: #57534e; margin-top: 0.15rem;}
.bb-dataline {font-size: 0.85rem; color: #57534e; margin: -0.2rem 0 0.2rem;}
.bb-sortline {font-size: 0.82rem; color: #1c1917; margin: 0 0 0.35rem;}
.bb-modeline {font-size: 0.85rem; color: #57534e; line-height: 1.45;}
.bb-modeline b {color: #1c1917;}
.bb-metrics {display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 12px;}
.bb-metric {border: 1px solid rgba(49, 51, 63, 0.18); border-radius: 0.6rem; padding: 0.8rem 1rem;
    background: #fff;}
.bb-metric-label {font-size: 0.85rem; color: #57534e; line-height: 1.3; white-space: normal;}
.bb-metric-value {font-size: 1.65rem; font-weight: 650; color: #1c1917; line-height: 1.25; margin-top: 0.2rem;}
.bb-metric-caption {font-size: 0.78rem; color: #57534e; line-height: 1.35; margin-top: 0.25rem;}
.bb-card-title {font-size: 1.12rem; font-weight: 700; color: #123554; margin: 0;}
.bb-card-subtitle {font-size: 0.85rem; color: #57534e; margin: 0.1rem 0 0.5rem;}
ul.bb-rank {list-style: none; margin: 0 !important; padding: 0 !important;}
.bb-rank li {display: flex; align-items: center; justify-content: space-between; gap: 10px;
    padding: 0.38rem 0; border-bottom: 1px solid #f0efed; font-size: 0.92rem; color: #1c1917;}
.bb-rank li:last-child {border-bottom: none;}
.bb-rank .bb-place {flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.bb-rank .bb-num {color: #57534e; display: inline-block; min-width: 1.7em;}
.bb-rank .bb-side {font-size: 0.82rem; color: #57534e; white-space: nowrap;}
.bb-rank .bb-val {font-size: 0.85rem; color: #1c1917; white-space: nowrap; flex: 0 0 4.3em; text-align: right;}
.bb-rank .bb-level {min-width: 5.6em;}
.bb-rank li.bb-head {font-size: 0.75rem; color: #57534e; padding-top: 0;}
.bb-rank li.bb-head .bb-val {font-size: 0.75rem; color: #57534e; white-space: normal; line-height: 1.15;}
.bb-dot {display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 0.35rem;
    border: 1px solid rgba(0, 0, 0, 0.25); vertical-align: 0;}
.bb-badge {display: inline-block; padding: 0.12rem 0.6rem; border-radius: 999px; font-size: 0.78rem;
    font-weight: 650; white-space: nowrap;}
.bb-plan-summary {margin: 0.5rem 0 0.2rem; font-size: 0.9rem; color: #1c1917; line-height: 1.45;}
.bb-legend {display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 0.84rem; color: #1c1917;
    margin-top: 0.35rem; align-items: center;}
.bb-legend span.bb-key {display: inline-flex; align-items: center; gap: 6px;}
.bb-swatch {display: inline-block; width: 14px; height: 14px; border-radius: 3px;}
.bb-maptitle {font-size: 1.12rem; font-weight: 700; color: #123554; margin: 0;}
.bb-mapnote {font-size: 0.86rem; color: #1c1917; margin: 0.1rem 0 0.3rem;}
.bb-adv-head {display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 0.95rem;
    color: #1c1917;}
.bb-adv-body {font-size: 0.92rem; color: #1c1917; line-height: 1.5;}
.bb-adv-heading {font-weight: 650; margin-bottom: 0.2rem;}
.bb-adv-groups {background: #f5f4f1; border-radius: 0.4rem; padding: 0.45rem 0.7rem; margin: 0.3rem 0 0.4rem;
    font-size: 0.88rem;}
.bb-adv-label {margin-bottom: 0.15rem;}
ul.bb-adv-bullets {margin: 0.2rem 0 0 1.1rem !important; padding: 0 !important;}
ul.bb-adv-bullets li {margin: 0.1rem 0;}
.bb-compare-title {font-size: 0.98rem; font-weight: 650; color: #1c1917;}
.bb-compare-note {font-size: 0.82rem; color: #57534e; line-height: 1.35; margin-bottom: 0.3rem; min-height: 2.3em;}
.bb-copy {background: #fff; border: 1px solid rgba(49, 51, 63, 0.25); border-radius: 0.5rem; padding: 0.3rem 0.9rem;
    font-size: 0.85rem; color: #1c1917; cursor: pointer; float: right;}
.bb-copy:hover {border-color: #D5581C; color: #D5581C;}
.bb-pending {display: inline-block; font-size: 0.78rem; font-weight: 650; color: #7c2d12; background: #ffedd5;
    border: 1px solid #fdba74; border-radius: 999px; padding: 0.1rem 0.6rem;}
.bb-banner {border-left: 4px solid #123554; background: #eef2f7; padding: 0.55rem 0.9rem; border-radius: 0.3rem;
    font-size: 0.92rem; color: #1c1917; margin-bottom: 0.6rem;}
</style>
"""


# Streamlit removes inline onclick attributes, so one listener on the page serves every Copy button
COPY_SCRIPT = """
<script>
if (!window.bbCopyListener) {
  window.bbCopyListener = true;
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".bb-copy");
    if (!button) return;
    navigator.clipboard.writeText(button.dataset.text).then(() => {
      button.textContent = "Copied";
      setTimeout(() => { button.textContent = "Copy"; }, 1500);
    });
  });
}
</script>
"""


def esc(text):
    """HTML-escape text."""
    return html.escape(str(text))


def apply_style():
    """Page-wide CSS and the click handler of the Copy buttons."""
    st.html(STYLE)
    st.html(COPY_SCRIPT, unsafe_allow_javascript=True)


def active_menu_style(url_path):
    """Navy background for the open page in the side menu; Streamlit marks it only with generated class names."""
    link = f'[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href="{esc(url_path)}"]'
    st.html(f"<style>{link}, {link}:hover {{background: #123554;}} {link} p {{color: #ffffff; font-weight: 600;}}"
            "</style>")


def badge(label, color):
    """Pill with the risk color as background and readable text."""
    text = "#ffffff" if color in DARK_FILLS else INK
    return f'<span class="bb-badge" style="background:{color};color:{text}">{esc(label)}</span>'


def risk_badge(level):
    """Badge for a risk level."""
    return badge(level, RISK_COLORS[str(level)])


def metric_cards(items):
    """Metric cards in a grid that wraps, so labels are never cut off; items are (label, value, caption[, hover])."""
    cards = "".join(f'<div class="bb-metric" title="{esc(hover[0]) if hover else ""}">'
                    f'<div class="bb-metric-label">{esc(label)}</div><div class="bb-metric-value">{esc(value)}</div>'
                    f'<div class="bb-metric-caption">{esc(caption)}</div></div>'
                    for label, value, caption, *hover in items)
    st.html(f'<div class="bb-metrics">{cards}</div>')


def chance_text(p_exposed):
    """Chance of being reached as a whole percent, such as 92%."""
    return f"{p_exposed:.0%}"


def rise_text(pct_rise):
    """Rise in risk with one decimal, such as +2.5%."""
    return f"+{pct_rise:.1f}%"


def banner(text):
    """Blue-edged note at the top of a page."""
    st.html(f'<div class="bb-banner">{text}</div>')


def mode_switch():
    """Daily outlook or Eruption response, shared by every page, with one line on each."""
    st.segmented_control("Mode", dd.MODES, default=dd.MODES[0], key="mode", required=True,
                         persist_state="session", label_visibility="collapsed")
    mode = dd.mode_selected()
    lines = "<br>".join(f"<b>{esc(name)}:</b> {esc(text)}" if name == mode else f"{esc(name)}: {esc(text)}"
                        for name, text in MODE_LINES.items())
    st.html(f'<div class="bb-modeline">{lines}</div>')
    return mode


def focus_banner(view):
    """Which day a page uses, and where to change it."""
    mode = dd.mode_selected()
    banner(f"<b>{esc(dd.view_title(view))}</b>, {esc(mode.lower())}. This page follows the day last opened on "
           "Forecast or Replay past events.")


# Map

def map_rows(rows, eruption):
    """Fill color, hover text and click popup per barangay."""
    rows = rows.copy()
    if eruption:
        rows["fill"] = rows["exposure_tier"].map(TIER_COLORS)
        status = (f"{CHANCE_LABEL}: " + rows["p_exposed"].map(chance_text) + " ("
                  + rows["exposure_tier"].str.lower() + ")")
    else:
        rows["fill"] = rows["risk_level"].astype(str).map(RISK_COLORS)
        status = "Risk: " + rows["risk_level"].astype(str)
    rows["tooltip"] = [f"<b>{esc(n)}</b>, {esc(m)}<br>{esc(s)}"
                       for n, m, s in zip(rows["name"], rows["municipality_name"], status)]
    rows["popup"] = [risk_popup(row, eruption) for _, row in rows.iterrows()]
    return rows


def risk_popup(row, eruption):
    """Popup HTML for one barangay on the risk map."""
    facts = [("Risk level", row["risk_level"], ""),
             (CHANCE_LABEL, chance_text(row["p_exposed"]), CHANCE_HELP),
             (RISE_LABEL, rise_text(row["pct_rise_s40"]), RISE_HELP),
             ("Children under 5", f"{int(row['pop_under5']):,}", ""),
             ("Adults 60+", f"{int(row['pop_60plus']):,}", ""),
             ("Distance from the crater", f"{row['dist_km']:.1f} km", ""),
             ("Nearest health facility", row["nearest_facility_text"], "")]
    if row["downwind"]:
        facts.insert(1, ("Wind", "Downwind (inside the forecast plume)", ""))
    if eruption:
        facts.insert(0, ("Help-first rank", f"{row['priority_rank']} of {dd.N_BARANGAYS}", ""))
    table = "".join(f'<tr title="{esc(hover)}"><td style="color:{MUTED_INK};padding:1px 10px 1px 0">{esc(k)}</td>'
                    f'<td style="padding:1px 0">{esc(v)}</td></tr>' for k, v, hover in facts)
    reasons = ""
    if row["reasons"]:
        items = "".join(f"<li>{esc(r)}</li>" for r in row["reasons"])
        reasons = (f'<div style="margin-top:6px;font-weight:600">Main reasons for the chance of being reached</div>'
                   f'<ol style="margin:2px 0 0 16px;padding:0">{items}</ol>')
    return (f'<div style="font:12px system-ui,-apple-system,Segoe UI,sans-serif;color:{INK};min-width:290px">'
            f'<div style="font-size:14px;font-weight:600">{esc(row["name"])}</div>'
            f'<div style="color:{MUTED_INK};margin-bottom:4px">{esc(row["municipality_name"])}, '
            f'{esc(row["province"])}</div><table style="margin:0;border-collapse:collapse">{table}</table>'
            f'{reasons}</div>')


def legend(eruption, plume=True, observed=False, reported=False, extra=()):
    """Legend under the map; extra holds (label, swatch HTML) pairs."""
    colors = TIER_COLORS if eruption else RISK_COLORS
    title = "Where exposure is most likely:" if eruption else "Risk level:"
    keys = [(label, f'<span class="bb-swatch" style="background:{color};border:1px solid rgba(0,0,0,0.12)">'
                    '</span>') for label, color in colors.items()]
    if plume:
        keys.append(("Forecast plume", '<span class="bb-swatch" style="background:rgba(87,83,78,0.25);'
                                       'border:1px dashed #57534e"></span>'))
    if observed:
        keys.append(("Observed drift", '<span style="display:inline-block;width:22px;border-top:2.5px dashed '
                                       '#000"></span>'))
    if reported:
        keys.append(("Reported that day", '<span class="bb-swatch" style="background:#fff;border:3px solid '
                                          '#000"></span>'))
    keys += list(extra)
    keys.append(("10, 20 and 30 km from the crater", '<span style="display:inline-block;width:22px;border-top:'
                                                     '1.5px dashed #78716c"></span>'))
    items = "".join(f'<span class="bb-key">{swatch}{esc(label)}</span>' for label, swatch in keys)
    st.html(f'<div class="bb-legend"><b>{esc(title)}</b>{items}</div>')


def show_map(m, key, height=MAP_HEIGHT):
    """Render a folium map without sending map events back to the app."""
    st_folium(m, height=height, use_container_width=True, returned_objects=[], key=key)


def plume_title(view):
    """Map title from the forecast drift direction."""
    if view["drift_deg"] is None or pd.isna(view["drift_deg"]):
        return "Forecast plume: no drift forecast for this date"
    return f"Forecast plume: drifting {dd.direction_words(view['drift_deg'])}"


# Cards

def ranked(rows, eruption):
    """Rows in list order for the mode: who to serve first (eruption response) or risk rank."""
    return rows.sort_values("priority_rank" if eruption else "risk_rank")


def top_barangays_card(view, eruption):
    """Highest-risk barangays (daily outlook) or who to serve first (eruption response), top 10."""
    top = ranked(view["rows"], eruption).head(TOP_COUNT)
    items = []
    if eruption:
        items.append(f'<li class="bb-head"><span class="bb-place">Barangay</span><span class="bb-val" '
                     f'title="{esc(CHANCE_HELP)}">{CHANCE_LABEL}</span>'
                     '<span class="bb-val">Under 5 and 60+</span></li>')
    else:
        items.append(f'<li class="bb-head"><span class="bb-place">Barangay</span><span class="bb-val" '
                     f'title="{esc(RISE_HELP)}">{RISE_LABEL}</span>'
                     '<span class="bb-val bb-level">Risk level</span></li>')
    for i, row in enumerate(top.itertuples(), start=1):
        place = f"{row.name}, {row.municipality_name}"
        # the municipality is in the hover text so the name has room next to the two values
        if eruption:
            dot = f'<span class="bb-dot" style="background:{TIER_COLORS[row.exposure_tier]}"></span>'
            right = (f'<span class="bb-val">{chance_text(row.p_exposed)}</span>'
                     f'<span class="bb-val">{int(row.pop_vulnerable):,}</span>')
        else:
            dot = ""
            right = (f'<span class="bb-val">{rise_text(row.pct_rise_s40)}</span>'
                     f'<span class="bb-val bb-level">{risk_badge(row.risk_level)}</span>')
        items.append(f'<li><span class="bb-place" title="{esc(place)}"><span class="bb-num">{i}.</span>{dot}'
                     f'{esc(row.name)}</span>{right}</li>')
    title = "Who to serve first" if eruption else "Highest-risk barangays"
    if view["source"] == "forecast":
        when = "Forecast for tomorrow" if view["horizon"] == dd.HORIZONS[0] else f"Forecast for {view['horizon']}"
    else:
        when = f"Replay, {dd.short_date(view['day'])}"
    sort_line = SORT_LINES[dd.MODES[1] if eruption else dd.MODES[0]]
    with st.container(border=True):
        st.html(f'<div class="bb-card-title">{title}</div><div class="bb-card-subtitle">{esc(when)}</div>'
                f'<div class="bb-sortline">{esc(sort_line)}</div><ul class="bb-rank">{"".join(items)}</ul>')
        st.page_link("views/barangay_list.py", label="See all 216 barangays")


def resupply_card(view):
    """Default response plan (make_plan defaults) for the day on screen."""
    with st.container(border=True):
        st.html('<div class="bb-card-title">Resupply plan</div><div class="bb-card-subtitle">Default plan: '
                f'5 roving teams within 10 km, {allocation.SCENARIO_MASKS:,} masks, '
                f'{allocation.SCENARIO_KITS} nebulizer kits at the team bases</div>')
        try:
            plan = dd.response_plan(dd.plan_day_rows(view))
        except (ValueError, RuntimeError) as err:
            st.warning(f"No plan could be made for this day: {err}")
            return
        labels = dd.load_bases().set_index("base_id")["label"]
        items = "".join(f'<li><span class="bb-place" title="{esc(labels[b.base_id])}">{esc(labels[b.base_id])}'
                        f'</span><span class="bb-side">{b.kits} kits</span></li>'
                        for b in plan["bases"].sort_values("kits", ascending=False).itertuples())
        rows = plan["barangays"]
        covered = rows["covered"]
        vulnerable = int(rows.loc[covered, ["pop_under5", "pop_60plus"]].sum().sum())
        st.html(f'<ul class="bb-rank">{items}</ul><div class="bb-plan-summary">Teams cover <b>{int(covered.sum())} '
                f'of {dd.N_BARANGAYS}</b> barangays ({vulnerable:,} residents under 5 and 60+). '
                f'<b>{int(rows["masks"].sum()):,} masks</b> go to {int((rows["masks"] > 0).sum())} barangays, '
                'highest need first.</div>')
        st.page_link("views/response_planner.py", label="Open the response planner")


def grouped_barangays(rows):
    """Barangay names grouped by municipality, both in alphabetical order."""
    return [(municipality, sorted(group["name"])) for municipality, group in rows.groupby("municipality_name")]


def advisory_parts(rows, level, template, others_label, day):
    """Opening and risk-level sentences, place sections and advice of the advisory for one risk level.

    rows: every barangay on the day (after the municipality filter). Each section is (label or None, places), with
    places as (municipality, barangay names). Low lists municipality names only: first those with no barangay at a
    higher level, then, after others_label, those that also appear on a higher card.
    """
    opening, risk, *advice = (line.format(date=dd.short_date(day), risk_level=level)
                              for line in template.splitlines())
    groups = grouped_barangays(rows[rows["risk_level"] == level])
    if level == health.RISK_LEVELS[0]:
        higher = set(rows.loc[rows["risk_level"] > level, "municipality_name"])
        sections = [(None, [(municipality, []) for municipality, _ in groups if municipality not in higher]),
                    (others_label, [(municipality, []) for municipality, _ in groups if municipality in higher])]
    else:
        sections = [(None, groups)]
    return [opening, risk], [section for section in sections if section[1]], advice


def advisory_text(head, sections, advice):
    """Plain text of one advisory for copying, SMS and the download: head, place sections, bullets."""
    blocks = ["\n".join(head)]
    for label, places in sections:
        lines = [f"{municipality}: {', '.join(names)}" if names else municipality for municipality, names in places]
        blocks.append("\n".join([label, *lines] if label else lines))
    blocks.append("\n".join(f"- {line}" for line in advice))
    return "\n\n".join(blocks)


def advisory_html(head, sections, advice):
    """The same advisory as HTML for the on-screen card."""
    head_html = "".join(f'<div class="bb-adv-heading">{esc(line)}</div>' for line in head)
    section_html = ""
    for label, places in sections:
        label_html = f'<div class="bb-adv-label">{esc(label)}</div>' if label else ""
        place_html = "".join(f"<div><b>{esc(municipality)}:</b> {esc(', '.join(names))}</div>" if names
                             else f"<div><b>{esc(municipality)}</b></div>" for municipality, names in places)
        section_html += f'<div class="bb-adv-groups">{label_html}{place_html}</div>'
    advice_html = "".join(f"<li>{esc(line)}</li>" for line in advice)
    return f'<div class="bb-adv-body">{head_html}{section_html}<ul class="bb-adv-bullets">{advice_html}</ul></div>'


def copy_button(text):
    """Button that copies text to the clipboard (handled by COPY_SCRIPT)."""
    st.html(f'<button type="button" class="bb-copy" data-text="{esc(text)}">Copy</button>')


def advisory_levels(rows, include_low):
    """Risk levels with at least one barangay, highest first; Low only when asked for."""
    return [level for level in reversed(health.RISK_LEVELS)
            if (rows["risk_level"] == level).any() and (include_low or level != "Low")]


def advisories(view):
    """Advisories for residents: one card per risk level with its barangays, in the chosen language."""
    templates = load_language_templates()
    rows = view["rows"]
    st.html('<div class="bb-card-title">Daily advisory</div><div class="bb-card-subtitle">For residents. Share '
            'through barangay health workers, LGU pages, or SMS.</div>')
    controls = st.columns([2, 2, 1], vertical_alignment="bottom")
    with controls[0]:
        st.segmented_control("Language", LANGUAGES, default=LANGUAGES[0], key="language", required=True,
                             persist_state="session", width="stretch")
    municipalities = controls[1].multiselect("Municipality", sorted(rows["municipality_name"].unique()),
                                             key="advisory_municipalities", persist_state="session",
                                             placeholder="All municipalities")
    include_low = controls[2].checkbox("Include Low", key="advisory_include_low", persist_state="session")
    language = st.session_state.get("language") or LANGUAGES[0]
    if municipalities:
        rows = rows[rows["municipality_name"].isin(municipalities)]

    levels = advisory_levels(rows, include_low)
    if not levels:
        where = " in the selected municipalities" if municipalities else ""
        st.info(f"No barangay is at Moderate or higher on this day{where}. Tick Include Low to see the Low "
                "advisory.")
    for level in levels:
        level_rows = rows[rows["risk_level"] == level]
        template = templates[(level, language)]
        parts = advisory_parts(rows, level, template["text"], LOW_OTHERS_LABEL[language], view["day"])
        unreviewed = language != "English" and not template["reviewed_by"].strip()
        with st.container(border=True):
            top = st.columns([5, 1], vertical_alignment="center")
            note = ' <span class="bb-pending">Pending review</span>' if unreviewed else ""
            count = f"{len(level_rows)} barangay{'s' if len(level_rows) > 1 else ''}"
            top[0].html(f'<div class="bb-adv-head">{risk_badge(level)}<b>{count}</b>{note}</div>')
            with top[1]:
                copy_button(advisory_text(*parts))
            st.html(advisory_html(*parts))
            if language != "English" and template["back_translation_english"]:
                with st.expander("Back-translation to English"):
                    st.text(advisory_text(*advisory_parts(rows, level, template["back_translation_english"],
                                                          LOW_OTHERS_LABEL["English"], view["day"])))

    st.html('<div class="bb-card-subtitle" style="margin-top:0.6rem">Download all advisories (.txt): every risk '
            'level on this day, Low included, for the selected municipalities.</div>')
    downloads = st.columns(len(LANGUAGES))
    all_levels = advisory_levels(rows, include_low=True)
    for col, download_language in zip(downloads, LANGUAGES):
        texts = [advisory_text(*advisory_parts(rows, level, templates[(level, download_language)]["text"],
                                               LOW_OTHERS_LABEL[download_language], view["day"]))
                 for level in all_levels]
        col.download_button(f"{download_language} (.txt)", CARD_SEPARATOR.join(texts).encode("utf-8"),
                            file_name=f"advisories_{view['day']}_{download_language.lower()}.txt",
                            mime="text/plain", width="stretch", disabled=not texts)
    st.caption("Advice follows general DOH and PHIVOLCS guidance for ashfall and volcanic gas.")


@st.cache_data
def load_language_templates():
    """Advisory templates keyed by (risk level, language)."""
    return {(row["level"], row["language"]): row for row in dd.load_templates().to_dict("records")}


# The Figure A3 layout shared by Forecast and Replay past events

def day_metrics(view):
    """Four headline numbers for the day on screen."""
    rows = view["rows"]
    so2 = view["so2_td"]
    so2_value = f"{so2:,.0f} t/d" if pd.notna(so2) else "None"
    drift = view["drift_deg"]
    has_drift = drift is not None and pd.notna(drift)
    drift_value = dd.direction_words(drift).capitalize() if has_drift else "None"
    drift_caption = (f"Wind at plume height (Open-Meteo, 06:00 to 18:00): toward {drift:.0f} degrees at "
                     f"{view['wind_speed']:.1f} m/s." if has_drift else "No wind data that day.")
    if view["source"] == "forecast":
        so2_caption = (f"Forecast from PHIVOLCS data up to {dd.short_date(view['last_data_date'])}. Days 2 and 3 "
                       "reuse this value.")
    else:
        observed = view["observed_so2"]
        so2_caption = ("Forecast made the day before. "
                       + (f"Measured that day: {observed:,.0f} t/d." if pd.notna(observed)
                          else "No measurement that day."))
        model_deg = view["drift_model_deg"]
        drift_caption += (f" Drift model ({view['drift_model']}) forecast: "
                          f"{dd.direction_words(model_deg) if model_deg is not None else 'none'}. "
                          + (f"Observed by PHIVOLCS: {dd.direction_words(view['observed_deg'])}."
                             if view["observed_deg"] is not None else "No PHIVOLCS observation that day."))
    moderate_up = int((rows["risk_level"] >= "Moderate").sum())
    top = rows.loc[rows["pct_rise_s40"].idxmax()]
    metric_cards([
        ("Forecast SO2 emission", so2_value, so2_caption),
        ("Forecast plume drift", drift_value, drift_caption),
        ("Barangays Moderate or higher", f"{moderate_up} of {dd.N_BARANGAYS}",
         "Risk level Moderate, High or Very high"),
        ("Highest rise in risk", rise_text(top["pct_rise_s40"]),
         f"In {top['name']}, {top['municipality_name']}, compared with a normal day", RISE_HELP),
    ])


def eruption_note():
    """What eruption response shows, for health workers."""
    st.info("Use after PHIVOLCS reports an eruption. Dark red barangays are the most likely to get ash or gas. The "
            "list shows which barangays to help first. This tool does not predict eruptions.")


def compare_days(live, eruption):
    """Three small maps side by side, one per forecast day, each with its drift and count at Moderate or higher."""
    st.html('<div class="bb-maptitle">Compare 3 days</div>')
    columns = st.columns(len(dd.HORIZONS), gap="small")
    for col, horizon in zip(columns, dd.HORIZONS):
        view = dd.forecast_view(live, horizon)
        moderate_up = int((view["rows"]["risk_level"] >= "Moderate").sum())
        with col:
            st.html(f'<div class="bb-compare-title">{esc(horizon)}, {view["day"]:%a, %b} {view["day"].day}</div>'
                    f'<div class="bb-compare-note">Drifting {esc(dd.direction_words(view["drift_deg"]))} '
                    f'({view["drift_deg"]:.0f} degrees, {view["wind_speed"]:.1f} m/s). '
                    f'<b>{moderate_up} of {dd.N_BARANGAYS}</b> at Moderate or higher.</div>')
            m = risk_map.make_map(dd.load_polygons(), map_rows(view["rows"], eruption), plume_deg=view["drift_deg"])
            show_map(m, key=f"compare_{view['day']}_{eruption}", height=COMPARE_MAP_HEIGHT)
    legend(eruption)


def show_day(view, eruption, map_key):
    """Metrics, the risk map with plume wedge, highest-risk barangays, resupply plan and advisories."""
    dd.set_focus(view)
    day_metrics(view)
    if eruption:
        eruption_note()
    left, right = st.columns([1.6, 1], gap="medium")
    with left:
        st.html(f'<div class="bb-maptitle">{esc(plume_title(view))}</div>')
        if view["source"] == "replay":
            n_reported = len(view["reported"])
            st.html('<div class="bb-mapnote">'
                    + (f"<b>{n_reported} of {dd.N_BARANGAYS}</b> study barangays reported ashfall or sulfur odor "
                       "that day (black outline)." if n_reported else "No reports of ashfall or sulfur odor that "
                                                                       "day.") + "</div>")
        rows = map_rows(view["rows"], eruption)
        m = risk_map.make_map(dd.load_polygons(), rows, plume_deg=view["drift_deg"],
                              observed_deg=view["observed_deg"], reported=view["reported"])
        show_map(m, key=map_key, height=DAY_MAP_HEIGHT)
        legend(eruption, plume=view["drift_deg"] is not None, observed=view["observed_deg"] is not None,
               reported=bool(view["reported"]))
        st.caption(MAP_CAPTION)
        st.caption("Hover over a barangay for its risk level; click it for details and the main reasons.")
    with right:
        top_barangays_card(view, eruption)
        resupply_card(view)
    st.divider()
    advisories(view)
