"""Dependency-free static interactive track explorer."""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from loguru import logger

from ._site_frontend import SCRIPT, STYLE

HEAD_EXTRA = (
    '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>'
    '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
    '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
)


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def _variable_label(name: str, attrs: dict[str, Any]) -> str:
    labels = {
        "fco2_seawater": "Seawater fCO₂",
        "pco2_seawater": "Seawater pCO₂",
        "pco2_equilibrator": "Equilibrator pCO₂",
        "xco2_dry": "Dry-air xCO₂",
        "xco2_wet": "Wet-air xCO₂",
        "raw_co2": "Raw CO₂",
        "raw_watertemp": "Water temperature",
        "raw_salinity": "Salinity",
        "raw_watercond": "Water conductivity",
        "raw_chl_a": "Chlorophyll a",
        "oxygen": "Dissolved oxygen",
        "dissolved_oxygen": "Dissolved oxygen",
        "oxygen_concentration": "Dissolved oxygen",
        "doxy": "Dissolved oxygen",
        "o2": "Dissolved oxygen",
        "raw_oxygen": "Raw dissolved oxygen",
        "raw_o2": "Raw dissolved oxygen",
        "lat": "Latitude",
        "lon": "Longitude",
        "raw_latitude": "Raw latitude",
        "raw_longitude": "Raw longitude",
        "raw_speed": "Speed",
        "raw_course": "Course",
    }
    described = attrs.get("long_name") or attrs.get("standard_name")
    return labels.get(name, str(described) if described else name.replace("_", " ").title())


def _model(ds: xr.Dataset, max_points: int | None = None) -> dict[str, Any]:
    indices = np.arange(ds.sizes["time"])
    if max_points and len(indices) > max_points:
        indices = np.linspace(0, len(indices) - 1, max_points).astype(int)
    candidates = [
        name
        for name, arr in ds.data_vars.items()
        if arr.dims == ("time",) and np.issubdtype(arr.dtype, np.number) and name != "qc_flag"
    ]
    preferred = [
        name
        for name in (
            "fco2_seawater",
            "pco2_seawater",
            "raw_co2",
            "raw_watertemp",
            "raw_salinity",
            "raw_chl_a",
            "co2_flux",
        )
        if name in candidates
    ]
    oxygen_variables = [
        name
        for name in candidates
        if "oxygen" in name.lower()
        or name.lower() in {"o2", "doxy"}
        or name.lower().startswith(("o2_", "doxy_"))
    ]
    preferred.extend(name for name in oxygen_variables if name not in preferred)
    variables = preferred + [name for name in candidates if name not in preferred]
    fallback_units = {
        "raw_watertemp": "°C",
        "raw_salinity": "PSU",
        "raw_chl_a": "µg L⁻¹",
    }
    return {
        "time": [pd.Timestamp(item).isoformat() for item in ds.time.values[indices]],
        "lat": [_json_value(item) for item in ds.lat.values[indices]],
        "lon": [_json_value(item) for item in ds.lon.values[indices]],
        "qc": [int(item) for item in ds.qc_flag.values[indices]],
        "variables": variables,
        "variable_meta": {
            name: {
                "label": _variable_label(name, ds[name].attrs),
                "units": str(ds[name].attrs.get("units") or fallback_units.get(name, "")).replace(
                    "uatm", "µatm"
                ),
            }
            for name in variables
        },
        "data": {
            name: [_json_value(item) for item in ds[name].values[indices]] for name in variables
        },
    }


def _qc_help(config: dict[str, Any] | None) -> str:
    config = dict(config or {})
    rows = [
        ("Parse", "Record parsed successfully", "parse failure"),
        ("Time", "Valid UTC timestamp", "invalid time"),
        ("Position", "Finite; |latitude| ≤ 90°; |longitude| ≤ 180°; not 0°, 0°", "invalid position"),
    ]
    phases = config.get("analysis_phases", [5])
    if phases:
        rows.append(("Sampling phase", f"One of {', '.join(map(str, phases))}", "excluded phase"))
    if config.get("status_ok") is not None:
        rows.append(
            (
                "Instrument status",
                f"One of {', '.join(map(str, config['status_ok']))}",
                "instrument status",
            )
        )
    for label, key in (
        ("Water flow", "minimum_water_flow"),
        ("Gas flow", "minimum_gas_flow"),
    ):
        if key in config:
            rows.append((label, f"≥ {config[key]}", "flow"))
    ranges = {"co2": [100, 1000], "watertemp": [-2.5, 45], "salinity": [0, 45]}
    ranges.update(config.get("ranges", {}))
    range_labels = {
        "co2": ("CO₂", ""),
        "watertemp": ("Water temperature", " °C"),
        "salinity": ("Salinity", " PSU"),
    }
    for name, bounds in ranges.items():
        label, units = range_labels.get(name, (name.replace("_", " ").title(), ""))
        rows.append((label, f"{bounds[0]} to {bounds[1]}{units}", "physical range"))
    rows.extend(
        [
            ("Calibration", "Required calibration available", "missing calibration"),
            ("Collocation", "Within each product's configured tolerances", "collocation tolerance"),
        ]
    )
    body = "".join(
        f"<tr><th scope=row>{escape(check)}</th><td>{escape(accepted)}</td><td>{escape(flag)}</td></tr>"
        for check, accepted, flag in rows
    )
    return (
        '<span class=qc-popover id=qc-help role=tooltip><strong>QC-good means every applicable check passes</strong>'
        '<span class=qc-intro>With the filter enabled, any observation carrying one or more flags is hidden.</span>'
        '<span class=qc-table-wrap><table><thead><tr><th scope=col>Check</th><th scope=col>Accepted</th><th scope=col>Flag if failed</th></tr></thead>'
        f"<tbody>{body}</tbody></table></span></span>"
    )


def _body(title: str, qc_config: dict[str, Any] | None = None) -> str:
    qc_help = _qc_help(qc_config)
    return (
        f'<header class=masthead><div><p class=eyebrow>Yacht CO₂ campaign</p><h1>{title}</h1></div>'
        f'<span class=toggle-wrap><label class=toggle><input id=good type=checkbox checked aria-describedby=qc-help><span>QC-good only</span></label>{qc_help}</span></header>'
        f"<main>"
        f'<section class=panel id=infopanel><div class=panel-heading><div><p class=eyebrow>Overview</p><h2>Campaign</h2></div></div><div id=infobody></div></section>'
        f'<section class=panel><div class=panel-heading><div><p class=eyebrow>Route explorer</p><h2>Track</h2></div><label class=compact-field>Colour by<select id=map-variable aria-label="Map colour variable"></select></label></div><div id=map></div><div class=map-legend aria-label="Track colour scale"><strong class=legend-title id=legend-title></strong><span id=legend-min></span><span class=colour-bar></span><span id=legend-max></span></div></section>'
        f'<section class=charts-section><div class=section-heading><div><p class=eyebrow>Linked observations</p><h2>Time series</h2><p class=section-note>Click a point to move the map marker; drag to zoom and double-click to reset. Different units or scales use a labelled right axis automatically.</p></div><button class="button primary" id=add-chart type=button aria-label="Add time series">Add chart</button></div><div class=charts id=charts></div>'
        f'<output class=readout aria-live=polite><span class=readout-time id=readout-time></span><span class=readout-values id=readout-values></span></output></section>'
        f"</main>"
    )


def site_filename(campaign: str, campaign_date: str) -> str:
    """Name a single-file site after the campaign it describes.

    Campaign names carry spaces, punctuation and accents that make awkward
    URLs, so the ``<campaign>-<campaign date>.html`` name is slugified: lower
    case, with every run of other characters collapsed to one hyphen.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", f"{campaign}-{campaign_date}".lower()).strip("-")
    if not slug:
        raise ValueError("campaign and campaign date cannot both be empty")
    return f"{slug}.html"


def build_site(
    ds: xr.Dataset,
    destination: str | Path,
    *,
    title: str = "Yacht CO2 campaign",
    single_file: bool = False,
    max_points: int | None = None,
    report: dict[str, Any] | None = None,
    qc_config: dict[str, Any] | None = None,
) -> Path:
    """Build a hosted static bundle or fully self-contained HTML artifact.

    ``report`` is the summary dict produced by :func:`yacht_co2.report.summarise`
    (or loaded from a prior ``report.json``); when given, it is embedded as
    ``window.YACHT_REPORT`` and rendered as a campaign info panel. The map
    uses Leaflet and the time series uses Plotly, both from public CDNs, so
    viewing the site needs a plain static file server (e.g.
    ``python -m http.server`` or ``npx serve``) plus internet access -- no
    backend required.
    """
    destination = Path(destination)
    title = escape(title)
    model = json.dumps(_model(ds, max_points), separators=(",", ":"), allow_nan=False)
    report_json = json.dumps(report, separators=(",", ":"), allow_nan=False) if report else "null"
    data_script = f"window.YACHT_DATA={model};window.YACHT_REPORT={report_json};"
    if single_file:
        path = destination if destination.suffix == ".html" else destination / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        html = (
            f"<!doctype html><html><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width'><title>{title}</title>"
            f"<style>{STYLE}</style>{HEAD_EXTRA}</head><body>{_body(title, qc_config)}"
            f"<script>{data_script}</script><script>{SCRIPT}</script></body></html>"
        )
        path.write_text(html)
    else:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "style.css").write_text(STYLE)
        (destination / "app.js").write_text(SCRIPT)
        (destination / "data.js").write_text(data_script)
        path = destination / "index.html"
        path.write_text(
            f"<!doctype html><html><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width'><title>{title}</title>"
            f"<link rel=stylesheet href=style.css>{HEAD_EXTRA}</head><body>{_body(title, qc_config)}"
            f"<script src=data.js></script><script src=app.js></script></body></html>"
        )
    logger.success("Built static site {} ({:.1f} MiB)", path, path.stat().st_size / 2**20)
    return path
