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
from .schema import QCFlag

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


def _variables(ds: xr.Dataset) -> list[dict[str, Any]]:
    """Derived (non ``raw_``) track variables with their coverage and units.

    Ranges are taken over QC-good records only. Including flagged records makes
    the statistics unusable as a sanity check, since out-of-range values are
    exactly what QC flags.
    """
    good = np.asarray(ds.qc_flag.values, dtype="uint16") == 0
    entries = []
    for name, array in sorted(ds.data_vars.items()):
        if name.startswith("raw_") or name in _NOT_MEASUREMENTS or array.dims != ("time",):
            continue
        if not np.issubdtype(array.dtype, np.number):
            continue
        values = _finite(np.asarray(array.values, dtype=float)[good])
        entries.append(
            {
                "name": str(name),
                "units": str(array.attrs.get("units", "")),
                "valid": int(_finite(array.values).size),
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
    backs both ``report.json`` and ``REPORT.md``. Pure: it reads no files, so
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


def _table(rows: Sequence[Sequence[Any]], header: Sequence[str]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += [
        "| " + " | ".join("" if item is None else str(item) for item in row) + " |" for row in rows
    ]
    return lines


def render_markdown(summary: Mapping[str, Any]) -> str:
    """Render a summary as the human-readable ``REPORT.md``."""
    campaign = summary.get("campaign", summary.get("expedition", {}))
    temporal = summary["temporal"]
    spatial = summary["spatial"]
    quality = summary["quality"]
    provenance = summary["provenance"]

    lines = [f"# {campaign.get('name', 'Campaign')}", ""]
    lines += ["_Auto-generated by yacht-co2; do not edit by hand._", ""]

    lines += ["## Platform", ""]
    lines += _table(
        [[key, value] for key, value in campaign.items() if key != "name"],
        ["field", "value"],
    )

    lines += ["", "## Extent", ""]
    lines += _table(
        [
            ["start (UTC)", temporal["start"]],
            ["end (UTC)", temporal["end"]],
            ["duration (days)", temporal["days"]],
            ["latitude", f"{spatial.get('latitude_min')} to {spatial.get('latitude_max')}"],
            ["longitude", f"{spatial.get('longitude_min')} to {spatial.get('longitude_max')}"],
            ["valid positions", spatial.get("positions")],
        ],
        ["field", "value"],
    )

    lines += ["", "## Sampling", ""]
    lines += _table(
        [
            ["records", temporal["records"]],
            ["median interval (s)", temporal.get("median_interval_seconds")],
            [
                f"gaps >= {temporal.get('gap_threshold_minutes')} min",
                temporal.get("gap_count"),
            ],
            ["time in gaps (min)", temporal.get("gap_minutes")],
            ["coverage (%)", temporal.get("coverage_percent")],
        ],
        ["field", "value"],
    )

    lines += ["", "## Quality control", ""]
    lines += [
        f"{quality['good_records']} of {quality['total_records']} records carry no QC flag "
        f"({quality['good_percent']}%). Flags are bitwise, so the counts below overlap.",
        "",
    ]
    lines += (
        _table(
            sorted(quality["flag_counts"].items(), key=lambda item: -item[1]),
            ["flag", "records"],
        )
        if quality["flag_counts"]
        else ["No QC flags were raised."]
    )

    if summary["files"]:
        lines += ["", "## Source files", ""]
        lines += _table(
            [[item["name"], item["records"]] for item in summary["files"]],
            ["file", "records"],
        )

    if summary["variables"]:
        lines += ["", "## Variables", ""]
        lines += ["Ranges cover QC-good records only.", ""]
        lines += _table(
            [
                [
                    item["name"],
                    item["units"],
                    item["valid"],
                    item["good"],
                    item["min"],
                    item["max"],
                    item["mean"],
                ]
                for item in summary["variables"]
            ],
            ["variable", "units", "valid", "good", "min", "max", "mean"],
        )

    if summary["products"]:
        lines += ["", "## Products", ""]
        keys = sorted({key for status in summary["products"] for key in status})
        lines += _table([[status.get(key) for key in keys] for status in summary["products"]], keys)

    lines += ["", "## Provenance", ""]
    lines += _table(
        [[key, value] for key, value in provenance.items() if value],
        ["field", "value"],
    )

    if summary["artifacts"]:
        lines += ["", "## Artifacts", ""]
        lines += _table(list(summary["artifacts"].items()), ["kind", "path"])

    return "\n".join(lines) + "\n"


def write_report(summary: Mapping[str, Any], destination: str | Path) -> dict[str, Path]:
    """Write ``report.json`` and ``REPORT.md`` into ``destination``."""
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "report_json": destination / "report.json",
        "report_markdown": destination / "REPORT.md",
    }
    paths["report_json"].write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n")
    paths["report_markdown"].write_text(render_markdown(summary))
    logger.success("Wrote JSON report to {}", paths["report_json"])
    logger.success("Wrote Markdown report to {}", paths["report_markdown"])
    return paths
