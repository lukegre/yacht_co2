"""Run summary and provenance record for a processed campaign."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from loguru import logger

from .manifest import CampaignManifest
from .schema import QCFlag, phase_labels

REPORT_VERSION = "1.0.0"

#: Gaps at least this long are treated as the instrument not sampling rather
#: than as jitter in the logging interval. Matches the legacy report.
DEFAULT_GAP_THRESHOLD = pd.Timedelta("5min")


def _finite(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    return values[np.isfinite(values)]


def _round(value: float, digits: int = 3) -> float | None:
    return None if not np.isfinite(value) else round(float(value), digits)


def _temporal(time: np.ndarray, gap_threshold: pd.Timedelta) -> dict[str, Any]:
    stamps = pd.DatetimeIndex(pd.Series(time).dropna())
    if stamps.empty:
        return {"start": None, "end": None, "days": None, "records": 0}
    intervals = stamps.to_series().diff().iloc[1:]
    gaps = intervals[intervals >= gap_threshold]
    span_minutes = (stamps[-1] - stamps[0]).total_seconds() / 60
    gap_minutes = gaps.sum().total_seconds() / 60
    return {
        "start": stamps[0].isoformat(),
        "end": stamps[-1].isoformat(),
        "days": _round((stamps[-1] - stamps[0]).total_seconds() / 86400, 2),
        "records": int(len(stamps)),
        "median_interval_seconds": (
            None if intervals.empty else _round(intervals.median().total_seconds(), 1)
        ),
        "gap_threshold_minutes": _round(gap_threshold.total_seconds() / 60, 1),
        "gap_count": int(len(gaps)),
        "gap_minutes": _round(gap_minutes, 1),
        "coverage_percent": (
            None if span_minutes <= 0 else _round(100 * (1 - gap_minutes / span_minutes), 1)
        ),
    }


def _spatial(ds: xr.Dataset) -> dict[str, Any]:
    """Bounding box over positions that QC did not flag as invalid."""
    valid = (np.asarray(ds.qc_flag.values, dtype="uint16") & int(QCFlag.INVALID_POSITION)) == 0
    lat = _finite(np.asarray(ds.lat.values)[valid])
    lon = _finite(np.asarray(ds.lon.values)[valid])
    if not lat.size or not lon.size:
        return {"positions": 0}
    return {
        "positions": int(min(lat.size, lon.size)),
        "latitude_min": _round(lat.min()),
        "latitude_max": _round(lat.max()),
        "longitude_min": _round(lon.min()),
        "longitude_max": _round(lon.max()),
    }


def _quality(ds: xr.Dataset) -> dict[str, Any]:
    """Per-bit QC counts. Bits are not exclusive, so counts need not sum."""
    flags = np.asarray(ds.qc_flag.values, dtype="uint16")
    total = int(flags.size)
    good = int((flags == 0).sum())
    return {
        "total_records": total,
        "good_records": good,
        "flagged_records": total - good,
        "good_percent": None if not total else _round(100 * good / total, 1),
        "flag_counts": {
            str(flag.name).lower(): int((flags & int(flag)).astype(bool).sum())
            for flag in QCFlag
            if (flags & int(flag)).any()
        },
    }


#: Column holding the instrument's sampling phase. Matches the site's.
_PHASE_VARIABLE = "raw_sampling_phase"


#: Measured CO2 mole fraction, preferred in this order for the phase tally.
#: The logged column is the one that reads across every phase, which is what
#: makes the means comparable; a derived seawater fCO2 exists only where the
#: instrument was on seawater.
_PHASE_CO2_VARIABLES = ("raw_co2", "co2", "xco2_wet")


def _phase_co2(ds: xr.Dataset) -> tuple[str, np.ndarray, str] | None:
    """The CO2 column the phase tally averages, with its name and units."""
    for name in _PHASE_CO2_VARIABLES:
        if name in ds and ds[name].dims == ("time",):
            array = ds[name]
            return name, np.asarray(array.values, dtype=float), str(array.attrs.get("units", ""))
    return None


def _phases(ds: xr.Dataset, labels: Mapping[str, str]) -> list[dict[str, Any]]:
    """How many records the instrument logged in each sampling phase, and at what CO2.

    QC flags every phase outside the analysis set, so without this tally a
    campaign's flag counts say how much was excluded but not what it was: air
    standards, zero and span calibrations and seawater are all one number.

    The CO2 mean is taken over every finite reading in the phase, flagged
    included. It is there to say whether the instrument did what the phase
    asked -- a zero reading near zero, a span near its certified value -- and
    QC flags exactly those readings for being outside the seawater range, so
    a QC-good mean would be empty for the phases the mean is most use for.
    """
    if _PHASE_VARIABLE not in ds:
        return []
    codes = np.asarray(ds[_PHASE_VARIABLE].values, dtype=float)
    flags = np.asarray(ds.qc_flag.values, dtype="uint16")
    co2 = _phase_co2(ds)
    total = int(codes.size)
    entries = []
    # A missing phase is its own group, as it is on the page's phase picker.
    for code in sorted(set(np.where(np.isfinite(codes), codes, -1.0).tolist())):
        members = np.where(np.isfinite(codes), codes, -1.0) == code
        count = int(members.sum())
        entries.append(
            {
                "code": None if code == -1 else int(code),
                # A code the manifest does not name is still a real phase, so
                # it is numbered rather than lumped into an "other".
                "label": labels.get(
                    str(int(code)), "Unrecorded" if code == -1 else f"Phase {int(code)}"
                ),
                "records": count,
                "good_records": int((flags[members] == 0).sum()),
                "percent": None if not total else _round(100 * count / total, 1),
                **_phase_co2_summary(co2, members),
            }
        )
    return entries


def _phase_co2_summary(
    co2: tuple[str, np.ndarray, str] | None, members: np.ndarray
) -> dict[str, Any]:
    """Mean CO2 over one phase's finite readings, or nulls when it has none."""
    if co2 is None:
        return {
            "co2_variable": None,
            "co2_units": "",
            "co2_records": 0,
            "co2_mean": None,
            "co2_std": None,
        }
    name, values, units = co2
    finite = _finite(values[members])
    return {
        "co2_variable": name,
        "co2_units": units,
        "co2_records": int(finite.size),
        "co2_mean": _round(finite.mean(), 2) if finite.size else None,
        "co2_std": _round(finite.std(), 2) if finite.size else None,
    }


def _files(ds: xr.Dataset) -> list[dict[str, Any]]:
    if "source_file" not in ds:
        return []
    names, counts = np.unique(np.asarray(ds.source_file.values).astype(str), return_counts=True)
    return [
        {"name": str(name), "records": int(count)}
        for name, count in zip(names, counts, strict=False)
    ]


#: Position and bookkeeping variables reported elsewhere in the summary.
_NOT_MEASUREMENTS = frozenset({"lat", "lon", "qc_flag", "qc_good", "source_line"})
#: Logged columns reported despite the ``raw_`` prefix. Temperature and
#: salinity are the seawater state fCO2 is derived at, so a summary without
#: them cannot be sanity-checked against the water the campaign sailed through.
_REPORTED_RAW = ("raw_watertemp", "raw_salinity")


def _seawater(ds: xr.Dataset) -> np.ndarray:
    """Which records were sampling seawater, per the QC step's ``seawater`` column."""
    if "seawater" not in ds:
        return np.ones(int(ds.sizes["time"]), dtype=bool)
    return np.asarray(ds.seawater.values, dtype=bool)


def _variables(ds: xr.Dataset) -> list[dict[str, Any]]:
    """Derived track variables, and logged temperature and salinity, summarised.

    Ranges are taken over QC-good seawater records only. Flagged records would
    make the statistics unusable as a sanity check, since out-of-range values
    are exactly what QC flags; gas standards would do the same to a different
    end, since a seawater fCO2 derived from a zero is arithmetic on a number
    that was never seawater. The per-phase tally is where those readings are
    reported, and the page still plots them.
    """
    good = (np.asarray(ds.qc_flag.values, dtype="uint16") == 0) & _seawater(ds)
    entries = []
    for key, array in sorted(ds.data_vars.items()):
        # Xarray keys a dataset by Hashable; every name here is a string.
        name = str(key)
        if name.startswith("raw_") and name not in _REPORTED_RAW:
            continue
        if name in _NOT_MEASUREMENTS or array.dims != ("time",):
            continue
        if not np.issubdtype(array.dtype, np.number):
            continue
        values = _finite(np.asarray(array.values, dtype=float)[good])
        entries.append(
            {
                "name": name,
                "units": str(array.attrs.get("units", "")),
                "valid": int(_finite(array.values).size),
                # "good" counts the QC-good seawater records the stats use.
                "good": int(values.size),
                "min": _round(values.min()) if values.size else None,
                "max": _round(values.max()) if values.size else None,
                "mean": _round(values.mean()) if values.size else None,
            }
        )
    return entries


def summarise(
    ds: xr.Dataset,
    *,
    manifest: CampaignManifest | None = None,
    platform: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Path] | None = None,
    products: Sequence[Mapping[str, str]] | None = None,
    gap_threshold: str | pd.Timedelta = DEFAULT_GAP_THRESHOLD,
) -> dict[str, Any]:
    """Summarise a processed track into a JSON-serialisable record.

    Combines campaign identity, extent, sampling statistics, per-bit QC
    counts, variable inventory and provenance into the single structure that
    backs ``report.json``. Pure: it reads no files, so
    callers load ``platform`` themselves via
    :func:`~yacht_co2.project.load_platform`.

    Parameters
    ----------
    ds:
        Canonical track dataset, after QC.
    manifest:
        Manifest the run was configured by. Supplies campaign identity;
        without it the name falls back to the ``campaign`` dataset attribute.
    platform:
        Project-level platform defaults, typically the ``platform`` block of
        ``project.yaml``. The manifest's ``campaign`` block overrides these
        key by key.
    artifacts:
        Artifact inventory from :class:`~yacht_co2.pipeline.RunResult`.
    products:
        Per-product fetch statuses from the enrichment step.
    gap_threshold:
        Sampling gaps of at least this length count as missing coverage.
    """
    campaign = dict(platform or {})
    # Nearest configuration wins: the manifest describes one campaign and so
    # refines the installation-wide defaults.
    campaign.update(dict(manifest.campaign) if manifest else {})
    campaign.setdefault("name", ds.attrs.get("campaign", ds.attrs.get("expedition", "unknown")))
    root = Path.cwd()
    return {
        "report_version": REPORT_VERSION,
        "schema_version": str(ds.attrs.get("schema_version", "")),
        "campaign": campaign,
        "temporal": _temporal(ds.time.values, pd.Timedelta(gap_threshold)),
        "spatial": _spatial(ds),
        "quality": _quality(ds),
        "phases": _phases(ds, phase_labels(manifest.phases if manifest else None)),
        "files": _files(ds),
        "variables": _variables(ds),
        "products": [dict(status) for status in (products or [])],
        "provenance": {
            "manifest": _relative(manifest.path, root) if manifest else None,
            "manifest_sha256": (
                manifest.digest if manifest else ds.attrs.get("manifest_sha256") or None
            ),
            "code_sha256": ds.attrs.get("code_sha256") or None,
            "processing_history": str(ds.attrs.get("processing_history", "")),
        },
        "artifacts": {
            key: _relative(Path(value), root) for key, value in sorted((artifacts or {}).items())
        },
    }


def _relative(path: Path, root: Path) -> str:
    """Prefer a repo-relative path so reports do not leak absolute paths."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def write_report(
    summary: Mapping[str, Any], destination: str | Path, *, stem: str = "report"
) -> dict[str, Path]:
    """Write ``<stem>.json`` into ``destination``."""
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    paths = {"report_json": destination / f"{stem}.json"}
    paths["report_json"].write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n")
    logger.success("Wrote JSON report to {}", paths["report_json"])
    return paths
