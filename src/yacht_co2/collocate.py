"""Pointwise product collocation and atmospheric CO2 source selection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from .schema import QCFlag, attach_qc_metadata, role_codes


def _coord(ds: xr.Dataset, short: str, long: str) -> str | None:
    return short if short in ds.coords else long if long in ds.coords else None


def collocate_track(
    track: xr.Dataset,
    product: xr.Dataset,
    *,
    variables: list[str] | None = None,
    time_tolerance: str | pd.Timedelta = "12h",
    spatial_tolerance_degrees: float | None = None,
    prefix: str = "",
) -> xr.Dataset:
    """Nearest-neighbour collocate a gridded product onto a moving track."""
    result = track.copy()
    source = product.copy()
    lat_name = _coord(source, "lat", "latitude")
    lon_name = _coord(source, "lon", "longitude")
    if lat_name is None or lon_name is None or "time" not in source.coords:
        raise ValueError("product requires time, latitude/lat and longitude/lon coordinates")
    if "wind_speed" in source and "wind_speed_squared" not in source:
        source["wind_speed_squared"] = source.wind_speed**2
    if "u10" in source and "v10" in source:
        source["wind_speed_squared"] = source.u10**2 + source.v10**2
        source["wind_speed"] = np.sqrt(source.wind_speed_squared)
    variables = variables or [str(name) for name in source.data_vars]
    if "u10" in source and "v10" in source:
        variables = list(dict.fromkeys([*variables, "wind_speed", "wind_speed_squared"]))
    query_lon = result.lon.values.copy()
    if float(source[lon_name].min()) >= 0 and np.any(query_lon < 0):
        query_lon %= 360.0
    query = {
        "time": xr.DataArray(result.time.values, dims="observation"),
        lat_name: xr.DataArray(result.lat.values, dims="observation"),
        lon_name: xr.DataArray(query_lon, dims="observation"),
    }
    selected = source[variables].sel(query, method="nearest")
    selected_time = source.time.sel(time=query["time"], method="nearest").values
    time_offset = np.abs(selected_time - result.time.values).astype("timedelta64[ns]")
    bad = time_offset > np.timedelta64(pd.Timedelta(time_tolerance).value, "ns")
    selected_lat = source[lat_name].sel({lat_name: query[lat_name]}, method="nearest").values
    selected_lon = source[lon_name].sel({lon_name: query[lon_name]}, method="nearest").values
    lon_delta = np.abs(selected_lon - query_lon)
    lon_delta = np.minimum(lon_delta, 360.0 - lon_delta)
    distance = np.hypot(selected_lat - result.lat.values, lon_delta)
    if spatial_tolerance_degrees is not None:
        bad |= distance > spatial_tolerance_degrees
    for name in variables:
        output_name = f"{prefix}{name}"
        values = np.asarray(selected[name].values)
        if np.issubdtype(values.dtype, np.number):
            values = values.astype(float)
            values[bad] = np.nan
        result[output_name] = ("time", values)
        result[output_name].attrs.update(source.attrs)
    result[f"{prefix}time_offset_seconds"] = (
        "time",
        time_offset.astype("timedelta64[ns]").astype("int64") / 1e9,
    )
    result[f"{prefix}spatial_offset_degrees"] = ("time", distance)
    flags = result.qc_flag.values.copy()
    flags[bad] |= int(QCFlag.COLLOCATION_TOLERANCE)
    result["qc_flag"] = ("time", flags.astype("uint16"))
    attach_qc_metadata(result.qc_flag)
    return result


def _nearest_series(
    target: pd.DatetimeIndex, source_time: Any, source_value: Any, tolerance: str
) -> np.ndarray:
    series = pd.Series(np.asarray(source_value, dtype=float), index=pd.DatetimeIndex(source_time))
    series = series[np.isfinite(series)].sort_index()
    if series.empty:
        return np.full(len(target), np.nan)
    return series.reindex(target, method="nearest", tolerance=pd.Timedelta(tolerance)).to_numpy()


def resolve_air_co2(
    track: xr.Dataset,
    observations: xr.Dataset | None = None,
    noaa: xr.Dataset | None = None,
    config: Mapping[str, Any] | None = None,
    phases: Mapping[str, Any] | None = None,
) -> xr.Dataset:
    """Resolve atmospheric xCO2 by onboard → observations → NOAA priority.

    The onboard reading is only trustworthy while the inlet is actually
    sampling air, which is ``phases.air`` -- the manifest's own ``phases``
    block, so the codes agree with whatever QC and calibration used them for.
    """
    config = dict(config or {})
    result = track.copy()
    target = pd.DatetimeIndex(result.time.values)
    values = np.full(result.sizes["time"], np.nan)
    source = np.full(result.sizes["time"], "missing", dtype="U24")
    tolerance = str(config.get("time_tolerance", "7D"))
    if "raw_sampling_phase" in result and "xco2_dry" in result:
        phase = result.raw_sampling_phase.values.astype(float)
        air_phases = role_codes(phases, "air", [22])
        mask = np.isin(phase, air_phases) & np.isfinite(result.xco2_dry.values)
        onboard = _nearest_series(target, target[mask], result.xco2_dry.values[mask], tolerance)
        use = np.isfinite(onboard)
        values[use], source[use] = onboard[use], "onboard"
    for candidate, label in ((observations, "observations"), (noaa, "noaa_mbl")):
        if candidate is None:
            continue
        name = "xco2_air" if "xco2_air" in candidate else list(candidate.data_vars)[0]
        proposed = _nearest_series(target, candidate.time.values, candidate[name].values, tolerance)
        use = ~np.isfinite(values) & np.isfinite(proposed)
        values[use], source[use] = proposed[use], label
    result["xco2_air"] = ("time", values)
    result["air_co2_source"] = ("time", source)
    result.xco2_air.attrs["units"] = "umol mol-1"
    pressure = result.get("raw_airpres", xr.full_like(result.lat, 1013.25)) / 1013.25
    from .science import fugacity_factor

    temperature = result.get(
        "raw_airtemp", result.get("raw_watertemp", xr.zeros_like(result.lat) + 20)
    )
    result["fco2_air"] = result.xco2_air * pressure * fugacity_factor(temperature, pressure)
    result.fco2_air.attrs.update(units="uatm", note="dry atmospheric mole fraction times pressure")
    return result
