"""Headless tests of the dashboard with Streamlit AppTest: every page runs, and the main controls work.

Run from the repository root: python -m pytest tests
"""
import json
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.results_summary import model_results_table

APP = ROOT / "app" / "streamlit_app.py"
PAGES = ["views/forecast.py", "views/response_planner.py", "views/barangay_list.py", "views/replay.py",
         "views/methods_results.py"]
TIMEOUT_S = 120  # first runs load the models and solve the response plan


@pytest.fixture(autouse=True)
def offline():
    """Make the Open-Meteo wind forecast request fail, so tests need no network and show the fallback."""
    st.cache_data.clear()
    with mock.patch("requests.get", side_effect=requests.ConnectionError):
        yield


def open_page(page):
    """Run the app and switch to one page."""
    at = AppTest.from_file(str(APP), default_timeout=TIMEOUT_S).run()
    if page != PAGES[0]:
        at.switch_page(page).run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page):
    """Every page runs without an exception."""
    assert not open_page(page).exception


def test_forecast_falls_back_to_latest_replay_date():
    """Without the wind forecast, the Forecast page warns and shows the latest replay date."""
    at = open_page(PAGES[0])
    assert "could not be loaded" in at.warning[0].value


@pytest.mark.parametrize("page", ["views/forecast.py", "views/replay.py", "views/barangay_list.py"])
def test_eruption_response_mode(page):
    """Switching to Eruption response works and is kept in session state."""
    at = open_page(page)
    at.segmented_control(key="mode").set_value("Eruption response").run()
    assert not at.exception
    assert at.session_state["mode"] == "Eruption response"


def test_replay_quick_pick():
    """A quick-pick button sets the replay date."""
    at = open_page("views/replay.py")
    at.button[1].click().run()
    assert not at.exception
    assert at.session_state["replay_day"] == date(2024, 9, 11)


def test_response_planner_with_fewer_teams():
    """The response plan solves again after the number of teams changes."""
    at = open_page("views/response_planner.py")
    at.slider(key="plan_teams").set_value(3).run()
    assert not at.exception


def test_methods_results_status_matches_shared_code():
    """The Methods & results table shows the target status computed by src/results_summary.py."""
    metrics = json.loads((APP.parent / "data" / "metrics.json").read_text(encoding="utf-8"))
    at = open_page("views/methods_results.py")
    assert at.table[0].value["Status"].tolist() == model_results_table(metrics)["Status"].tolist()
