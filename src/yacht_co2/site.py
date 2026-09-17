"""Dependency-free static interactive track explorer."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from loguru import logger

from ._site_frontend import SCRIPT, STYLE
from .naming import output_name

# A page has to open over a phone connection and attach to an email, so the
# track is stepped down to fit rather than shipped whole.
SIZE_LIMIT = 10 * 2**20
# Below this the page stops being a track, so a budget is never met by thinning
# further; the page goes over instead, with the warning that says so.
MINIMUM_POINTS = 500
_MINIMUM_BUDGET = 64 * 2**10
# Column holding the instrument's sampling phase, kept whatever else is dropped
# so the page can be filtered by what the instrument was measuring.
PHASE_VARIABLE = "raw_sampling_phase"
# Columns the page cannot be drawn without, so a selection never excludes them.
REQUIRED_VARIABLES = ("time", "lat", "lon", "qc_flag", PHASE_VARIABLE)
_SIZE_UNITS = {
    "": 1,
    "b": 1,
    "kb": 10**3,
    "mb": 10**6,
    "gb": 10**9,
    "kib": 2**10,
    "mib": 2**20,
    "gib": 2**30,
}


def parse_size(value: int | float | str) -> int:
    """Read a byte budget written as a number or as ``"8 MB"``.

    A page budget is an email attachment limit, which is quoted in megabytes
    rather than in bytes, so the manifest may say either. Decimal units follow
    the SI meaning the limits are quoted in (``MB`` is 10⁶); ``MiB`` asks for
    the binary one.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"size must be a number or a string such as '10 MB', not {value!r}")
    if not isinstance(value, str):
        return int(value)
    match = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z]*)\s*", value)
    if not match or match[2].lower() not in _SIZE_UNITS:
        raise ValueError(f"{value!r} is not a size such as '10 MB', '512 kB' or '8 MiB'")
    return int(float(match[1]) * _SIZE_UNITS[match[2].lower()])


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


def select_variables(ds: xr.Dataset, requested: Sequence[str] | None) -> list[str]:
    """Name the plottable columns the page carries, honouring a selection.

    Every one-dimensional numeric column travels by default, which is what a
    first look at a campaign wants and also what makes the page large. A
    ``requested`` list keeps only those columns, in the order asked for; a name
    the dataset does not hold is reported and skipped rather than failing a run
    whose data is otherwise complete.
    """
    candidates = [
        name
        for name, arr in ds.data_vars.items()
        if arr.dims == ("time",) and np.issubdtype(arr.dtype, np.number) and name != "qc_flag"
    ]
    if requested is None:
        return candidates
    selected: list[str] = []
    missing: list[str] = []
    for name in requested:
        if name in candidates:
            if name not in selected:
                selected.append(name)
        elif name not in REQUIRED_VARIABLES:
            missing.append(name)
    if missing:
        logger.warning(
            "Site variables not in the track, so not plotted: {}", ", ".join(sorted(missing))
        )
    if not selected:
        logger.warning(
            "No requested site variable is in the track; keeping all {} instead", len(candidates)
        )
        return candidates
    return selected


# What a manifest's phase roles mean on the page; anything else is titled as
# written, so a campaign naming its own roles still reads.
_PHASE_ROLE_LABELS = {"analysis": "Seawater", "air": "Air", "zero": "Zero", "span": "Span"}


def _phase_codes(ds: xr.Dataset, indices: np.ndarray) -> list[int] | None:
    """Sampling phase per observation, or ``None`` when the logs held none."""
    if PHASE_VARIABLE not in ds:
        return None
    values = np.asarray(ds[PHASE_VARIABLE].values, dtype=float)[indices]
    # A missing phase is its own group, distinct from every code the log uses.
    return [-1 if not np.isfinite(item) else int(item) for item in values]


def _phase_labels(config: dict[str, Any] | None) -> dict[str, str]:
    """Name each phase code the manifest describes, ``{"5": "Seawater"}``."""
    labels: dict[str, str] = {}
    for role, codes in (config or {}).items():
        if isinstance(codes, (int, float)) and not isinstance(codes, bool):
            codes = [codes]
        if isinstance(codes, str) or not isinstance(codes, Sequence):
            continue
        for code in codes:
            if isinstance(code, bool) or not isinstance(code, (int, float)):
                continue
            labels[str(int(code))] = _PHASE_ROLE_LABELS.get(str(role), str(role).title())
    return labels


def _model(
    ds: xr.Dataset,
    max_points: int | None = None,
    variables: Sequence[str] | None = None,
    phase_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    indices = np.arange(ds.sizes["time"])
    if max_points and len(indices) > max_points:
        indices = np.linspace(0, len(indices) - 1, max_points).astype(int)
    candidates = select_variables(ds, variables)
    if variables is not None:
        # An explicit selection is itself an order of interest, so keep it.
        ordered = candidates
    else:
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
        ordered = preferred + [name for name in candidates if name not in preferred]
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
        # The sampling phase always travels, whatever the variable selection:
        # it is what the page filters by, not something it plots.
        "phase": _phase_codes(ds, indices),
        "phase_meta": phase_labels or {},
        "variables": ordered,
        "variable_meta": {
            name: {
                "label": _variable_label(name, ds[name].attrs),
                "units": str(ds[name].attrs.get("units") or fallback_units.get(name, "")).replace(
                    "uatm", "µatm"
                ),
            }
            for name in ordered
        },
        "data": {
            name: [_json_value(item) for item in ds[name].values[indices]] for name in ordered
        },
    }


def _qc_help(config: dict[str, Any] | None) -> str:
    config = dict(config or {})
    rows = [
        ("Parse", "Record parsed successfully", "parse failure"),
        ("Time", "Valid UTC timestamp", "invalid time"),
        (
            "Position",
            "Finite; |latitude| ≤ 90°; |longitude| ≤ 180°; not 0°, 0°",
            "invalid position",
        ),
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
        "<span class=qc-popover id=qc-help role=tooltip><strong>QC-good means every applicable check passes</strong>"
        "<span class=qc-intro>With the filter enabled, any observation carrying one or more flags is hidden.</span>"
        "<span class=qc-table-wrap><table><thead><tr><th scope=col>Check</th><th scope=col>Accepted</th><th scope=col>Flag if failed</th></tr></thead>"
        f"<tbody>{body}</tbody></table></span></span>"
    )


def _body(title: str, qc_config: dict[str, Any] | None = None) -> str:
    qc_help = _qc_help(qc_config)
    return (
        f"<header class=masthead><div><p class=eyebrow>Yacht CO₂ campaign</p><h1>{title}</h1></div>"
        f'<div class=masthead-controls><label class="compact-field phase-field" id=phase-field hidden>Sampling phase<select id=phase aria-label="Sampling phase to display"></select></label>'
        f"<span class=toggle-wrap><label class=toggle><input id=good type=checkbox checked aria-describedby=qc-help><span>QC-good only</span></label>{qc_help}</span></div></header>"
        f"<main>"
        f"<section class=panel id=infopanel><div class=panel-heading><div><p class=eyebrow>Overview</p><h2>Campaign</h2></div></div><div id=infobody></div></section>"
        f'<section class=panel><div class=panel-heading><div><p class=eyebrow>Route explorer</p><h2>Track</h2></div><label class=compact-field>Colour by<select id=map-variable aria-label="Map colour variable"></select></label></div><div id=map></div><div class=map-legend aria-label="Track colour scale"><strong class=legend-title id=legend-title></strong><span id=legend-min></span><span class=colour-bar></span><span id=legend-max></span></div></section>'
        f'<section class=charts-section><div class=section-heading><div><p class=eyebrow>Linked observations</p><h2>Time series</h2><p class=section-note>Click a point to move the map marker; drag to zoom and double-click to reset. Different units or scales use a labelled right axis automatically.</p></div><button class="button primary" id=add-chart type=button aria-label="Add time series">Add chart</button></div><div class=charts id=charts></div>'
        f"<output class=readout aria-live=polite><span class=readout-time id=readout-time></span><span class=readout-values id=readout-values></span></output></section>"
        f"</main>"
    )


def site_filename(campaign: str, campaign_date: str) -> str:
    """Name a single-file site after the campaign it describes."""
    return output_name(campaign, campaign_date, "site", "html")


def _fit_model(
    ds: xr.Dataset,
    max_points: int | None,
    budget: int,
    limit: int,
    variables: Sequence[str] | None = None,
    phase_labels: dict[str, str] | None = None,
) -> str:
    """Serialise the track, stepping through it until it fits ``budget`` bytes.

    A campaign logs a reading every few seconds, which is far denser than any
    screen can draw, so a page that would outgrow its budget takes an evenly
    spaced step through the track instead. The step is measured rather than
    guessed: each attempt scales the point count by how far over budget the
    last one was, which settles in two or three passes.
    """
    total = int(ds.sizes["time"])
    points = min(total, max_points) if max_points else total
    while True:
        model = json.dumps(
            _model(ds, points, variables, phase_labels), separators=(",", ":"), allow_nan=False
        )
        size = len(model.encode())
        if size <= budget or points <= MINIMUM_POINTS:
            break
        # 0.95 undershoots the target so the next pass is the last one.
        points = max(MINIMUM_POINTS, int(points * budget / size * 0.95))
    if points < total:
        logger.warning(
            "Stepped {} observations down to {} to keep the page within {:.1f} MB",
            total,
            points,
            limit / 10**6,
        )
    return model


def build_site(
    ds: xr.Dataset,
    destination: str | Path,
    *,
    title: str = "Yacht CO2 campaign",
    single_file: bool = True,
    max_points: int | None = None,
    max_bytes: int | float | str = SIZE_LIMIT,
    variables: Sequence[str] | None = None,
    report: dict[str, Any] | None = None,
    qc_config: dict[str, Any] | None = None,
    phase_config: dict[str, Any] | None = None,
) -> Path:
    """Build a self-contained HTML artifact, or a hosted static bundle.

    One file is the default: it opens from a file manager, attaches to an
    email and uploads to a record as it is, where a bundle needs a server.
    ``destination`` is that file, so nothing is nested in a folder of its own.

    The track is stepped down to whatever fits ``max_bytes`` -- 10 MiB by
    default, and a number of bytes or a size such as ``"8 MB"`` -- and
    ``max_points`` caps it further. ``variables`` names the columns the page
    carries, in the order the pickers offer them; by default it carries every
    numeric one, which is thorough and large. Time, position, QC flag and
    sampling phase always travel, since the page is drawn and filtered by them.
    ``phase_config`` is the manifest's ``phases`` block, which names the phase
    codes in the page's phase picker. ``report`` is the summary dict produced by
    :func:`yacht_co2.report.summarise` (or loaded from a prior ``report.json``);
    when given, it is embedded as ``window.YACHT_REPORT`` and rendered as a
    campaign info panel. The map uses Leaflet and the time series uses Plotly,
    both from public CDNs, so viewing the site needs internet access -- and, for
    a bundle, a plain static file server -- but no backend.
    """
    destination = Path(destination)
    title = escape(title)
    report_json = json.dumps(report, separators=(",", ":"), allow_nan=False) if report else "null"
    body = _body(title, qc_config)
    limit = parse_size(max_bytes)
    overhead = len(STYLE) + len(SCRIPT) + len(HEAD_EXTRA) + len(body) + len(report_json)
    model = _fit_model(
        ds,
        max_points,
        max(limit - overhead, _MINIMUM_BUDGET),
        limit,
        variables,
        _phase_labels(phase_config),
    )
    data_script = f"window.YACHT_DATA={model};window.YACHT_REPORT={report_json};"
    if single_file:
        path = destination if destination.suffix == ".html" else destination / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        html = (
            f"<!doctype html><html><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width'><title>{title}</title>"
            f"<style>{STYLE}</style>{HEAD_EXTRA}</head><body>{body}"
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
            f"<link rel=stylesheet href=style.css>{HEAD_EXTRA}</head><body>{body}"
            f"<script src=data.js></script><script src=app.js></script></body></html>"
        )
    logger.success("Built static site {} ({:.1f} MiB)", path, path.stat().st_size / 2**20)
    return path
