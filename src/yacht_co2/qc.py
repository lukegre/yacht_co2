"""Transparent, non-destructive quality control."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import xarray as xr
from loguru import logger

from .schema import QCFlag, attach_qc_metadata, phase_codes, role_codes


def _raw(ds: xr.Dataset, name: str) -> xr.DataArray | None:
    return ds.get(name) if name in ds else ds.get(f"raw_{name}")


def transition_lag_mask(
    ds: xr.Dataset,
    config: Mapping[str, Any] | None = None,
    phases: Mapping[str, Any] | None = None,
) -> np.ndarray:
    """Which records fall in the settling stretch after a phase transition.

    The instrument does not answer for the new phase the instant it switches
    to it: the cell still holds the previous phase's gas or water, and the
    reading walks to its new value. ``qc.phase_transition_lag`` says how long
    that takes, in seconds, for each phase role -- a zero settles at a
    different rate to the seawater line -- and every record within that many
    seconds of the phase starting is flagged.

    The roles are the manifest's own ``phases`` roles, so a lag naming a role
    the campaign does not describe is a mistake rather than a silent no-op.

    Raises
    ------
    ValueError
        If a lag names a role absent from the ``phases`` block, or its value
        is not a non-negative number of seconds.
    """
    lags = dict(dict(config or {}).get("phase_transition_lag") or {})
    mask = np.zeros(ds.sizes["time"], dtype=bool)
    if not lags:
        return mask
    roles = phase_codes(phases)
    unknown = sorted(set(map(str, lags)) - set(roles))
    if unknown:
        known = ", ".join(sorted(roles)) or "none"
        raise ValueError(
            f"qc.phase_transition_lag names phase(s) {', '.join(unknown)}, "
            f"which the manifest's phases block does not describe (it has: {known})"
        )
    phase = _raw(ds, "sampling_phase")
    if phase is None:
        return mask
    values = np.asarray(phase.values, dtype=float)
    times = ds.time.values.astype("datetime64[ns]")
    # Where the phase changes, a new stretch of that phase begins; the first
    # record of the campaign starts one too.
    starts = np.flatnonzero(np.r_[True, values[1:] != values[:-1]])
    entered = np.repeat(times[starts], np.diff(np.r_[starts, len(values)]))
    elapsed = (times - entered) / np.timedelta64(1, "s")
    for role, seconds in lags.items():
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise ValueError(
                f"qc.phase_transition_lag.{role} must be a number of seconds, not {seconds!r}"
            )
        if seconds < 0:
            raise ValueError(f"qc.phase_transition_lag.{role} must not be negative")
        in_role = np.isin(values, np.asarray(roles[str(role)], dtype=float))
        mask |= in_role & (elapsed < float(seconds))
    return mask


def seawater_mask(ds: xr.Dataset, phases: Mapping[str, Any] | None = None) -> np.ndarray:
    """Which records were sampling seawater, per the manifest's ``phases.analysis``.

    The instrument cycles between seawater and its gas standards, and only the
    seawater stretch is a measurement of the ocean. This is the selector for a
    seawater product; it is deliberately not a QC flag, because a zero or span
    reading is a correct reading of something else, not a bad reading of water.
    """
    phase = _raw(ds, "sampling_phase")
    allowed = role_codes(phases, "analysis", [5])
    if phase is None or not allowed:
        return np.ones(ds.sizes["time"], dtype=bool)
    return np.isin(np.asarray(phase.values, dtype=float), np.asarray(allowed, dtype=float))


def apply_qc(
    ds: xr.Dataset,
    config: Mapping[str, Any] | None = None,
    phases: Mapping[str, Any] | None = None,
) -> xr.Dataset:
    """Set QC bits while preserving all observations and existing flags.

    The configured checks describe what seawater should look like -- a CO2
    range, a salinity range, a water flow -- so they are asked only of the
    records that were sampling seawater. A gas standard reading 0 ppm is not
    out of range; it is a zero doing its job, and flagging it as bad hides the
    records a calibration is checked by. Records outside the analysis phases
    therefore pass QC, and :func:`seawater_mask` is what selects water.

    Record-integrity flags set during ingest -- parse, time and position --
    are untouched here and apply in every phase. So does the transition lag:
    the settling stretch after a switch is a bad reading of whichever phase it
    belongs to, seawater or gas standard alike.

    Parameters
    ----------
    ds:
        Canonical track dataset.
    config:
        QC settings. Recognised keys are ``status_ok``, ``minimum_water_flow``,
        ``minimum_gas_flow``, ``ranges`` and ``phase_transition_lag``.
    phases:
        The manifest's ``phases`` block, naming the phase codes each role
        covers. ``seawater_mask`` reads ``phases.analysis`` from it, and
        ``phase_transition_lag`` is keyed by its role names.
    """
    config = dict(config or {})
    result = ds.copy()
    flags = result.qc_flag.values.astype("uint16", copy=True)
    seawater = seawater_mask(result, phases)
    status = _raw(result, "status")
    if status is not None and config.get("status_ok") is not None:
        values = np.asarray(status.values).astype(str)
        bad = ~np.isin(values, np.asarray(config["status_ok"]).astype(str))
        flags[seawater & bad] |= int(QCFlag.INSTRUMENT_STATUS)
    for name, setting in (("waterflow", "minimum_water_flow"), ("flowgas", "minimum_gas_flow")):
        array = _raw(result, name)
        if array is not None and setting in config:
            values = np.asarray(array.values, dtype=float)
            bad = ~np.isfinite(values) | (values < float(config[setting]))
            flags[seawater & bad] |= int(QCFlag.FLOW)
    default_ranges = {"co2": [100, 1000], "watertemp": [-2.5, 45], "salinity": [0, 45]}
    ranges = {**default_ranges, **config.get("ranges", {})}
    for name, bounds in ranges.items():
        array = _raw(result, name)
        if array is None:
            continue
        values = np.asarray(array.values, dtype=float)
        bad = ~np.isfinite(values) | (values < bounds[0]) | (values > bounds[1])
        flags[seawater & bad] |= int(QCFlag.PHYSICAL_RANGE)
    settling = transition_lag_mask(result, config, phases)
    flags[settling] |= int(QCFlag.TRANSITION_LAG)
    result["qc_flag"] = ("time", flags)
    attach_qc_metadata(result.qc_flag)
    result["qc_good"] = ("time", flags == 0)
    result.qc_good.attrs.update(description="true only when no QC bit is set")
    result["seawater"] = ("time", seawater)
    result.seawater.attrs.update(
        description="true where the instrument was sampling seawater",
        note="selector for a seawater product; not a quality judgement",
    )
    result.attrs["processing_history"] = result.attrs.get("processing_history", "") + "; QC"
    logger.info(
        "QC retained {} of {} rows with no flags ({} sampling seawater)",
        int((flags == 0).sum()),
        len(flags),
        int(seawater.sum()),
    )
    if settling.any():
        logger.info("{} rows flagged as settling after a phase transition", int(settling.sum()))
    return result
