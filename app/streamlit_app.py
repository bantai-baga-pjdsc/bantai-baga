"""BantAI Baga dashboard: barangay respiratory risk from Kanlaon SO2 and ash, response plans and advisories.

Run from the repository root: streamlit run app/streamlit_app.py
"""
from pathlib import Path

import streamlit as st
from PIL import Image

import components as ui
import dashboard_data as dd

ASSETS = Path(__file__).resolve().parent / "assets"
ICON = str(ASSETS / "bantai_baga_icon.png")
LOGO = Image.open(ASSETS / "bantai_baga_logo.png")
LOGO = LOGO.crop(LOGO.getbbox())  # trim the transparent margin so the logo fills its height

st.set_page_config(page_title="BantAI Baga", page_icon=ICON, layout="wide", initial_sidebar_state="auto")
st.logo(LOGO, size="large", icon_image=ICON)
ui.apply_style()

PAGES = [
    st.Page("views/forecast.py", title="Forecast", default=True),
    st.Page("views/response_planner.py", title="Response planner"),
    st.Page("views/barangay_list.py", title="Barangay list"),
    st.Page("views/replay.py", title="Replay past events"),
    st.Page("views/methods_results.py", title="Methods & results"),
]
page = st.navigation(PAGES, position="hidden")
ui.active_menu_style(page.url_path)

with st.sidebar:
    st.html(f'<div class="bb-tagline">Kanlaon respiratory risk forecast for {dd.N_BARANGAYS} barangays</div>')
    for menu_page in PAGES:
        st.page_link(menu_page, width="stretch")
    st.html('<div class="bb-footnote">Supports, but does not replace, PHIVOLCS and DOH decisions.</div>')

page.run()
