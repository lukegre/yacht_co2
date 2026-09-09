"""CO2 calibration, carbonate gas corrections, and air-sea flux."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import xarray as xr
from loguru import logger

from .schema import QCFlag, attach_qc_metadata


def _values(ds: xr.Dataset, *names: str) -> xr.DataArray:
    for name in names:
        if name in ds:
            return ds[name]
        if f"raw_{name}" in ds:
            return ds[f"raw_{name}"]
    raise KeyError(f"none of these variables is available: {', '.join(names)}")


def calibrate_co2(ds: xr.Dataset, config: Mapping[str, Any] | None = None) -> xr.Dataset:
    """Calibrate measured wet xCO2 using instrument or zero/span coefficients.

    ``method: instrument`` accepts the logger's already calibrated ``raw_co2``.
    ``method: linear`` applies ``(raw - zero_measured) * span_certified /
    (span_measured - zero_measured)``. Scalars or time-aligned arrays work.
    """
    config = dict(config or {})
    result = ds.copy()
    raw = _values(result, str(config.get("input", "co2"))).astype(float)
    method = config.get("method", "instrument")
    if method == "instrument":
        calibrated = raw
    elif method == "linear":
        zero = config.get("zero_measured")
        span = config.get("span_measured")
        standards = config.get("standards", {})
        certified = config.get("span_certified", standards.get("span"))
        if zero is None or span is None:
            phase = result.get("raw_sampling_phase")
            if phase is not None:
                zero = _phase_interpolation(
                    result.time.values,
                    raw.values,
                    phase.values,
                    [config.get("zero_phase", 2)],
                )
                span = _phase_interpolation(
                    result.time.values,
                    raw.values,
                    phase.values,
                    config.get("span_phases", [1, 15]),
                )
        if zero is None or span is None or certified is None:
            flags = result.qc_flag.values.copy()
            flags |= int(QCFlag.MISSING_CALIBRATION)
            result["qc_flag"] = ("time", flags.astype("uint16"))
            attach_qc_metadata(result.qc_flag)
            result["xco2_wet"] = xr.full_like(raw, np.nan, dtype=float)
            logger.warning("Linear calibration settings are incomplete")
            return result
        denominator = np.asarray(span) - np.asarray(zero)
        calibrated = (raw - zero) * float(certified) / denominator
    else:
        raise ValueError("calibration method must be 'instrument' or 'linear'")
    result["xco2_wet"] = calibrated
    result.xco2_wet.attrs.update(units="umol mol-1", long_name="calibrated wet CO2 mole fraction")
    result.attrs["calibration_method"] = str(method)
    return result


def _phase_interpolation(
    time: Any, values: Any, phases: Any, selected_phases: list[int]
) -> np.ndarray | None:
    """Interpolate medians of contiguous calibration episodes over observation time."""
    time_ns = np.asarray(time).astype("datetime64[ns]").astype("int64")
    values = np.asarray(values, dtype=float)
    selected = np.isin(np.asarray(phases, dtype=float), selected_phases) & np.isfinite(values)
    starts = np.flatnonzero(selected & ~np.r_[False, selected[:-1]])
    stops = np.flatnonzero(selected & ~np.r_[selected[1:], False]) + 1
    if not len(starts):
        return None
    event_time = np.array(
        [np.median(time_ns[start:stop]) for start, stop in zip(starts, stops, strict=True)]
    )
    event_value = np.array(
        [np.median(values[start:stop]) for start, stop in zip(starts, stops, strict=True)]
    )
    return np.interp(time_ns, event_time, event_value)


def derive_pco2(ds: xr.Dataset, config: Mapping[str, Any] | None = None) -> xr.Dataset:
    """Derive dry xCO2 and sea-surface pCO2 in microatmospheres.

    Water vapour is expected in mmol/mol (the OceanPack ``H2O``/ppt field).
    The dry mole fraction is multiplied by dry equilibrator pressure before the
    Takahashi (1993) exponential temperature correction is applied.
    """
    config = dict(config or {})
    result = ds.copy()
    wet = _values(result, "xco2_wet")
    h2o = _values(result, str(config.get("h2o", "h2o"))).astype(float)
    pressure = _values(result, str(config.get("pressure", "cellpress"))).astype(float)
    equ_temp = _values(result, str(config.get("equilibrator_temperature", "celltemp"))).astype(
        float
    )
    sea_temp = _values(result, str(config.get("sea_temperature", "watertemp"))).astype(float)
    vapour_fraction = h2o / float(config.get("h2o_scale", 1000.0))
    xdry = wet / (1.0 - vapour_fraction)
    dry_pressure = pressure * (1.0 - vapour_fraction)
    p_equ = xdry * dry_pressure / 1013.25
    p_sea = p_equ * np.exp(
        float(config.get("temperature_coefficient", 0.0423)) * (sea_temp - equ_temp)
    )
    result["xco2_dry"] = xdry
    result["pco2_equilibrator"] = p_equ
    result["pco2_seawater"] = p_sea
    for name in ("xco2_dry", "pco2_equilibrator", "pco2_seawater"):
        result[name].attrs["units"] = "uatm" if name.startswith("pco2") else "umol mol-1"
    result.pco2_seawater.attrs["temperature_correction"] = "exp(0.0423 * (T_sea - T_equ))"
    return result


def fugacity_factor(temperature_c: Any, pressure_atm: Any = 1.0) -> Any:
    """Return the Weiss (1974) virial fugacity factor for CO2 in air."""
    kelvin = np.asarray(temperature_c) + 273.15
    delta = 57.7 - 0.118 * kelvin
    b = -1636.75 + 12.0408 * kelvin - 0.0327957 * kelvin**2 + 3.16528e-5 * kelvin**3
    return np.exp(np.asarray(pressure_atm) * (b + 2 * delta) / (83.1451 * kelvin))


def derive_fco2(ds: xr.Dataset) -> xr.Dataset:
    """Convert seawater pCO2 to fCO2 using the Weiss virial correction."""
    result = ds.copy()
    temperature = _values(result, "watertemp")
    try:
        pressure_atm = _values(result, "airpres") / 1013.25
    except KeyError:
        pressure_atm = xr.ones_like(temperature)
    result["fco2_seawater"] = result.pco2_seawater * fugacity_factor(temperature, pressure_atm)
    result.fco2_seawater.attrs.update(units="uatm", long_name="sea-surface CO2 fugacity")
    return result


def schmidt_number_co2(temperature_c: Any) -> Any:
    """Wanninkhof (2014) seawater CO2 Schmidt number."""
    t = np.asarray(temperature_c)
    return 2116.8 - 136.25 * t + 4.7353 * t**2 - 0.092307 * t**3 + 0.0007555 * t**4


def solubility_co2(temperature_c: Any, salinity: Any) -> Any:
    """Weiss (1974) CO2 solubility in mol m-3 atm-1."""
    tk = np.asarray(temperature_c) + 273.15
    s = np.asarray(salinity)
    tk100 = tk / 100.0
    ln_k0 = (
        -58.0931
        + 90.5069 * (100.0 / tk)
        + 22.2940 * np.log(tk100)
        + s * (0.027766 - 0.025888 * tk100 + 0.0050578 * tk100**2)
    )
    return np.exp(ln_k0) * 1000.0


def derive_flux(ds: xr.Dataset, config: Mapping[str, Any] | None = None) -> xr.Dataset:
    """Calculate bulk air-sea CO2 flux, positive for ocean outgassing.

    Uses Wanninkhof (2014), ``k = 0.251 U10² (Sc/660)^-1/2``. Wind-squared
    products can be supplied as ``wind_speed_squared`` to avoid interpolation
    bias; otherwise ``wind_speed`` is squared locally.
    """
    config = dict(config or {})
    result = ds.copy()
    temperature = _values(result, str(config.get("temperature", "watertemp"))).astype(float)
    salinity = _values(result, str(config.get("salinity", "salinity"))).astype(float)
    if "wind_speed_squared" in result:
        wind2 = result.wind_speed_squared
    else:
        wind2 = _values(result, str(config.get("wind", "wind_speed"))).astype(float) ** 2
    sea = _values(result, str(config.get("sea_fco2", "fco2_seawater"))).astype(float)
    air = _values(result, str(config.get("air_fco2", "fco2_air"))).astype(float)
    sc = schmidt_number_co2(temperature)
    k_cm_hr = float(config.get("coefficient", 0.251)) * wind2 * (sc / 660.0) ** -0.5
    k_m_day = k_cm_hr * 0.24
    k0 = solubility_co2(temperature, salinity)
    flux = k_m_day * k0 * (sea - air) * 1e-6
    valid = (
        np.isfinite(temperature)
        & np.isfinite(salinity)
        & np.isfinite(wind2)
        & np.isfinite(sea)
        & np.isfinite(air)
    )
    flux = flux.where(valid)
    result["gas_transfer_velocity"] = k_m_day
    result["co2_solubility"] = xr.DataArray(k0, dims=("time",), coords={"time": result.time})
    result["co2_flux"] = flux
    result.gas_transfer_velocity.attrs.update(units="m day-1", formulation="Wanninkhof 2014")
    result.co2_solubility.attrs["units"] = "mol m-3 atm-1"
    result.co2_flux.attrs.update(units="mol m-2 day-1", positive="ocean to atmosphere")
    logger.success("Calculated air-sea CO2 flux")
    return result
