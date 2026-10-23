"""Folium maps for the dashboard: barangays, 10/20/30 km rings, forecast plume wedge and observed drift."""
import html

import folium
import numpy as np
from branca.element import MacroElement
from jinja2 import Template

from src import geo

RING_KM = [10, 20, 30]
STUDY_RADIUS_KM = RING_KM[-1]
PLUME_WIDTH_DEG = 45
ARROW_KM = (3, 26)
ARC_STEP_DEG = 2
INK = "#1c1917"
RING_COLOR = "#78716c"
PLUME_COLOR = "#57534e"
EDGE_COLOR = "#ffffff"
REPORTED_COLOR = "#000000"
BASE_COLOR = "#1d5fb4"
LABEL_HALO = "0 0 2px #fff, 0 0 2px #fff, 0 0 3px #fff"
FONT = "system-ui,-apple-system,'Segoe UI',sans-serif"

CRATER_ICON = ('<svg width="18" height="16" viewBox="0 0 18 16"><polygon points="9,1 17,15 1,15" '
               f'fill="{INK}" stroke="#fff" stroke-width="1.5"/></svg>')
RECENTER_ICON = (f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="{INK}" stroke-width="2" '
                 'stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="6.5"/>'
                 f'<circle cx="12" cy="12" r="1.6" fill="{INK}" stroke="none"/>'
                 '<path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg>')


def default_bounds():
    """Map bounds that center the crater and show the whole 30 km ring."""
    lat_n, _ = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, 0, STUDY_RADIUS_KM + 1)
    lat_s, _ = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, 180, STUDY_RADIUS_KM + 1)
    _, lon_e = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, 90, STUDY_RADIUS_KM + 1)
    _, lon_w = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, 270, STUDY_RADIUS_KM + 1)
    return [[float(lat_s), float(lon_w)], [float(lat_n), float(lon_e)]]


class RecenterControl(MacroElement):
    """Map button that returns to the default view."""

    _template = Template("""
        {% macro header(this, kwargs) %}
        <style>
        .recenter-control {width:34px;height:34px;padding:0;background:#fff;border:2px solid rgba(0,0,0,0.2);
            border-radius:4px;display:flex;align-items:center;justify-content:center;cursor:pointer;}
        .recenter-control:hover {background:#f4f4f4;}
        </style>
        {% endmacro %}
        {% macro script(this, kwargs) %}
        (function () {
            var map = {{ this._parent.get_name() }};
            var control = L.control({position: "topleft"});
            control.onAdd = function () {
                var button = L.DomUtil.create("button", "recenter-control");
                button.type = "button";
                button.innerHTML = {{ this.icon|tojson }};
                button.title = "Re-center map";
                button.setAttribute("aria-label", "Re-center map");
                L.DomEvent.disableClickPropagation(button);
                L.DomEvent.on(button, "click", function () { map.fitBounds({{ this.bounds|tojson }}); });
                return button;
            };
            control.addTo(map);
        })();
        {% endmacro %}
    """)

    def __init__(self, bounds):
        super().__init__()
        self._name = "RecenterControl"
        self.bounds = bounds
        self.icon = RECENTER_ICON


def lonlat(lat, lon):
    """GeoJSON coordinate pairs (longitude, latitude) from latitude and longitude arrays."""
    return np.column_stack([np.atleast_1d(lon), np.atleast_1d(lat)]).round(5).tolist()


def add_shape(m, geometry, style):
    """Non-interactive GeoJSON shape, so hover and clicks reach the barangays underneath."""
    folium.GeoJson({"type": "Feature", "geometry": geometry, "properties": {}},
                   style_function=lambda _: style, interactive=False).add_to(m)


def add_label(m, lat, lon, text, size=12, weight=500, color=INK, anchor=(0, 0)):
    """Plain text on the map with a white halo."""
    folium.Marker(
        [float(lat), float(lon)], interactive=False,
        icon=folium.DivIcon(html=f'<div style="font:{weight} {size}px {FONT};color:{color};white-space:nowrap;'
                                 f'text-shadow:{LABEL_HALO};pointer-events:none">{html.escape(text)}</div>',
                            icon_size=(0, 0), icon_anchor=anchor),
    ).add_to(m)


def add_rings(m):
    """Dashed rings at 10, 20 and 30 km from the crater, labeled east of the crater."""
    bearings = np.arange(0, 360 + ARC_STEP_DEG, ARC_STEP_DEG)
    for km in RING_KM:
        lat, lon = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, bearings, km)
        add_shape(m, {"type": "LineString", "coordinates": lonlat(lat, lon)},
                  {"color": RING_COLOR, "weight": 1.6 if km == STUDY_RADIUS_KM else 1, "dashArray": "5 6",
                   "opacity": 0.9})
        lat, lon = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, 96, km)
        add_label(m, lat, lon, f"{km} km", size=11, color="#57534e", anchor=(36, 0))


def add_plume_wedge(m, drift_deg, label="Forecast plume"):
    """Translucent gray sector from the crater, 45 degrees wide and 30 km long, centered on the drift direction."""
    bearings = np.arange(drift_deg - PLUME_WIDTH_DEG / 2, drift_deg + PLUME_WIDTH_DEG / 2 + 0.1, 1.5)
    lat, lon = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, bearings, STUDY_RADIUS_KM)
    crater = [[geo.CRATER_LON, geo.CRATER_LAT]]
    add_shape(m, {"type": "Polygon", "coordinates": [crater + lonlat(lat, lon) + crater]},
              {"color": PLUME_COLOR, "weight": 1.2, "dashArray": "4 4", "fillColor": PLUME_COLOR,
               "fillOpacity": 0.22})
    lat, lon = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, drift_deg, STUDY_RADIUS_KM * 0.62)
    add_label(m, lat, lon, label, size=12, weight=600, anchor=(40, 8))


def add_drift_arrow(m, drift_deg, label="Observed drift"):
    """Dashed arrow from the crater in the observed drift direction."""
    start, end = ARROW_KM
    lat, lon = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, drift_deg, np.array([start, end]))
    add_shape(m, {"type": "LineString", "coordinates": lonlat(lat, lon)},
              {"color": REPORTED_COLOR, "weight": 2.5, "dashArray": "7 6"})
    tip = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, drift_deg, end + 1.6)
    base_lat, base_lon = geo.destination_point(lat[-1], lon[-1], np.array([drift_deg - 90, drift_deg + 90]), 0.9)
    head = lonlat(*tip) + lonlat(base_lat, base_lon) + lonlat(*tip)
    add_shape(m, {"type": "Polygon", "coordinates": [head]},
              {"color": REPORTED_COLOR, "weight": 1, "fillColor": REPORTED_COLOR, "fillOpacity": 1})
    label_lat, label_lon = geo.destination_point(geo.CRATER_LAT, geo.CRATER_LON, drift_deg, end + 3.5)
    add_label(m, label_lat, label_lon, label, size=12, weight=600, anchor=(40, 8))


def add_crater(m):
    """Crater marker labeled Kanlaon."""
    folium.Marker([geo.CRATER_LAT, geo.CRATER_LON], tooltip="Kanlaon crater",
                  icon=folium.DivIcon(html=CRATER_ICON, icon_size=(18, 16), icon_anchor=(9, 8))).add_to(m)
    add_label(m, geo.CRATER_LAT, geo.CRATER_LON, "Kanlaon", size=13, weight=700, anchor=(27, 26))


def add_barangays(m, polygons, rows, reported=frozenset(), faded=frozenset()):
    """Barangay polygons filled with rows["fill"]; reported barangays get a thick black outline and are drawn last.

    rows: psgc_code, fill, tooltip and popup (HTML) per barangay. faded barangays get a lighter fill.
    """
    props = rows.set_index("psgc_code")[["fill", "tooltip", "popup"]]
    features = [{"type": "Feature", "geometry": f["geometry"],
                 "properties": {**props.loc[f["properties"]["psgc_code"]].to_dict(),
                                "reported": f["properties"]["psgc_code"] in reported,
                                "faded": f["properties"]["psgc_code"] in faded}}
                for f in polygons["features"]]
    features.sort(key=lambda f: f["properties"]["reported"])
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        style_function=lambda f: {
            "fillColor": f["properties"]["fill"],
            "fillOpacity": 0.3 if f["properties"]["faded"] else 0.8,
            "color": REPORTED_COLOR if f["properties"]["reported"] else EDGE_COLOR,
            "weight": 3 if f["properties"]["reported"] else 0.7},
        highlight_function=lambda f: {"color": INK, "weight": 3.5 if f["properties"]["reported"] else 2},
        tooltip=folium.GeoJsonTooltip(fields=["tooltip"], labels=False, sticky=True,
                                      style=f"font:13px {FONT};color:{INK};"),
        popup=folium.GeoJsonPopup(fields=["popup"], labels=False, max_width=360),
    ).add_to(m)


def add_team_bases(m, bases, chosen, reach_km):
    """Chosen team bases with their reach (straight-line radius) and the other candidate facilities as small dots."""
    for base in bases[~bases["base_id"].isin(chosen)].itertuples():
        folium.CircleMarker([base.lat, base.lon], radius=3, color="#57534e", weight=1, fill=True,
                            fill_color="#57534e", fill_opacity=0.6,
                            tooltip=f"{base.label} (candidate, not chosen)").add_to(m)
    for base in bases[bases["base_id"].isin(chosen)].itertuples():
        lat, lon = geo.destination_point(base.lat, base.lon, np.arange(0, 362, 2), reach_km)
        add_shape(m, {"type": "LineString", "coordinates": lonlat(lat, lon)},
                  {"color": BASE_COLOR, "weight": 1.5, "dashArray": "3 4"})
        folium.CircleMarker([base.lat, base.lon], radius=8, color="#fff", weight=2, fill=True,
                            fill_color=BASE_COLOR, fill_opacity=1, tooltip=base.tooltip).add_to(m)


def make_map(polygons, rows, plume_deg=None, observed_deg=None, reported=frozenset(), faded=frozenset(),
             team_bases=None):
    """Risk map: barangays, rings, crater, optional plume wedge, observed drift arrow and team bases.

    team_bases: (bases table with label and tooltip columns, chosen base ids, reach in km) or None.
    """
    bounds = default_bounds()
    m = folium.Map(location=[geo.CRATER_LAT, geo.CRATER_LON], zoom_start=10, zoom_snap=0.25,
                   tiles="Esri.WorldGrayCanvas", control_scale=True)
    m.fit_bounds(bounds)
    add_barangays(m, polygons, rows, reported, faded)
    add_rings(m)
    if plume_deg is not None:
        add_plume_wedge(m, plume_deg)
    if observed_deg is not None:
        add_drift_arrow(m, observed_deg)
    if team_bases is not None:
        add_team_bases(m, *team_bases)
    add_crater(m)
    RecenterControl(bounds).add_to(m)
    return m
