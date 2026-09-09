"""Transparent, non-destructive quality control."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import xarray as xr
from loguru import logger

from .schema import QCFlag, attach_qc_metadata


def _raw(ds: xr.Dataset, name: str) -> xr.DataArray | None:
    return ds.get(name) if name in ds else ds.get(f"raw_{name}")


def apply_qc(ds: xr.Dataset, config: Mapping[str, Any] | None = None) -> xr.Dataset:
    """Set QC bits while preserving all observations and existing flags.

    Parameters
    ----------
    ds:
        Canonical track dataset.
    config:
        QC settings. Recognised keys are ``analysis_phases``, ``status_ok``,
        ``minimum_water_flow``, ``minimum_gas_flow`` and ``ranges``.
    """
    config = dict(config or {})
    result = ds.copy()
    flags = result.qc_flag.values.astype("uint16", copy=True)
    phase = _raw(result, "sampling_phase")
    allowed = config.get("analysis_phases", [5])
    if phase is not None and allowed:
        values = np.asarray(phase.values, dtype=float)
        flags[~np.isin(values, np.asarray(allowed, dtype=float))] |= int(QCFlag.EXCLUDED_PHASE)
    status = _raw(result, "status")
    if status is not None and config.get("status_ok") is not None:
        values = np.asarray(status.values).astype(str)
        flags[~np.isin(values, np.asarray(config["status_ok"]).astype(str))] |= int(
            QCFlag.INSTRUMENT_STATUS
        )
    for name, setting in (("waterflow", "minimum_water_flow"), ("flowgas", "minimum_gas_flow")):
        array = _raw(result, name)
        if array is not None and setting in config:
            values = np.asarray(array.values, dtype=float)
            flags[~np.isfinite(values) | (values < float(config[setting]))] |= int(QCFlag.FLOW)
    default_ranges = {"co2": [100, 1000], "watertemp": [-2.5, 45], "salinity": [0, 45]}
    ranges = {**default_ranges, **config.get("ranges", {})}
    for name, bounds in ranges.items():
        array = _raw(result, name)
        if array is None:
            continue
        values = np.asarray(array.values, dtype=float)
        bad = ~np.isfinite(values) | (values < bounds[0]) | (values > bounds[1])
        flags[bad] |= int(QCFlag.PHYSICAL_RANGE)
    result["qc_flag"] = ("time", flags)
    attach_qc_metadata(result.qc_flag)
    result["qc_good"] = ("time", flags == 0)
    result.qc_good.attrs.update(description="true only when no QC bit is set")
    result.attrs["processing_history"] = result.attrs.get("processing_history", "") + "; QC"
    logger.info("QC retained {} of {} rows with no flags", int((flags == 0).sum()), len(flags))
    return result
