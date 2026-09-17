"""Canonical dataset and quality-control contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import IntFlag
from typing import Any

import numpy as np
import xarray as xr

SCHEMA_VERSION = "1.0.0"


class QCFlag(IntFlag):
    """Stable uint16 quality-control bit assignments."""

    PARSE_FAILURE = 1
    INVALID_TIME = 2
    INVALID_POSITION = 4
    #: No longer set. A record outside the analysis phases is a correct
    #: reading of a gas standard, not a bad reading of seawater, so the phase
    #: is carried by the ``seawater`` variable instead of judged here. The bit
    #: keeps its value so archived tracks still decode.
    EXCLUDED_PHASE = 8
    INSTRUMENT_STATUS = 16
    FLOW = 32
    PHYSICAL_RANGE = 64
    MISSING_CALIBRATION = 128
    COLLOCATION_TOLERANCE = 256
    #: Set on the settling stretch at the start of a sampling phase, where the
    #: cell still holds the previous phase's gas or water.
    TRANSITION_LAG = 512


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


# What a manifest's phase roles mean where they are shown; anything else is
# titled as written, so a campaign naming its own roles still reads.
_PHASE_ROLE_LABELS = {"analysis": "Seawater", "air": "Air", "zero": "Zero", "span": "Span"}


def phase_codes(config: Mapping[str, Any] | None) -> dict[str, list[int]]:
    """Read a manifest's ``phases`` block as ``role -> phase codes``.

    ``{"analysis": 5}`` and ``{"analysis": [5]}`` both read back as
    ``{"analysis": [5]}``; a role naming nothing usable is left out.
    """
    roles: dict[str, list[int]] = {}
    for role, codes in (config or {}).items():
        if isinstance(codes, (int, float)) and not isinstance(codes, bool):
            codes = [codes]
        if isinstance(codes, str) or not isinstance(codes, Sequence):
            continue
        usable = [
            int(code)
            for code in codes
            if not isinstance(code, bool) and isinstance(code, (int, float))
        ]
        if usable:
            roles[str(role)] = usable
    return roles


def role_codes(phases: Mapping[str, Any] | None, role: str, default: list[int]) -> list[int]:
    """Read one role's phase codes from a manifest's ``phases`` block.

    ``phases`` is the one place a campaign declares what its phase codes mean,
    so every consumer -- QC, calibration, the atmosphere step -- reads its
    codes through here rather than keeping its own copy. A manifest that
    omits the role keeps behaving as it always has: ``default`` is what a
    campaign gets for free.
    """
    return phase_codes(phases).get(role, default)


def phase_labels(config: Mapping[str, Any] | None) -> dict[str, str]:
    """Name each phase code a manifest's ``phases`` block describes.

    ``{"analysis": [5]}`` reads back as ``{"5": "Seawater"}``, which is what
    the page's phase picker and the report's phase tally are titled by.
    """
    labels: dict[str, str] = {}
    for role, codes in phase_codes(config).items():
        for code in codes:
            labels[str(code)] = _PHASE_ROLE_LABELS.get(role, role.title())
    return labels
