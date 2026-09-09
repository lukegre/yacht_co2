"""Canonical dataset and quality-control contracts."""

from __future__ import annotations

from enum import IntFlag

import numpy as np
import xarray as xr

SCHEMA_VERSION = "1.0.0"


class QCFlag(IntFlag):
    """Stable uint16 quality-control bit assignments."""

    PARSE_FAILURE = 1
    INVALID_TIME = 2
    INVALID_POSITION = 4
    EXCLUDED_PHASE = 8
    INSTRUMENT_STATUS = 16
    FLOW = 32
    PHYSICAL_RANGE = 64
    MISSING_CALIBRATION = 128
    COLLOCATION_TOLERANCE = 256


QC_MASKS = np.array([int(flag) for flag in QCFlag], dtype="uint16")
QC_MEANINGS = " ".join(str(flag.name).lower() for flag in QCFlag)


def attach_qc_metadata(array: xr.DataArray) -> xr.DataArray:
    """Attach CF-style flag metadata to a QC array."""
    array.attrs.update(
        flag_masks=QC_MASKS,
        flag_meanings=QC_MEANINGS,
        valid_min=np.uint16(0),
        valid_max=np.uint16(sum(QC_MASKS)),
    )
    return array


def validate_dataset(ds: xr.Dataset) -> xr.Dataset:
    """Validate the invariant portions of the canonical track schema."""
    if "time" not in ds.dims:
        raise ValueError("canonical dataset must have a 'time' dimension")
    for name in ("lat", "lon", "source_file", "qc_flag"):
        if name not in ds:
            raise ValueError(f"canonical dataset is missing {name!r}")
        if ds[name].dims != ("time",):
            raise ValueError(f"{name!r} must be one-dimensional over time")
    if ds.qc_flag.dtype != np.dtype("uint16"):
        raise ValueError("qc_flag must use uint16")
    if ds.sizes["time"] and not np.all(np.diff(ds.time.values) >= np.timedelta64(0, "ns")):
        raise ValueError("time must be monotonically increasing")
    ds.attrs.setdefault("schema_version", SCHEMA_VERSION)
    ds.time.attrs.setdefault("timezone", "UTC")
    return ds
