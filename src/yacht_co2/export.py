"""Lossless scientific exports and a documented flattened CSV view."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import xarray as xr
from loguru import logger

from .schema import validate_dataset


def netcdf_encoding(ds: xr.Dataset, complevel: int = 4) -> dict[str, dict[str, Any]]:
    """Return zlib encoding for every numeric variable and coordinate.

    Strings and objects are left alone: h5netcdf stores them as variable-length
    types, which the deflate filter cannot compress, and so are scalars, which
    cannot be chunked.
    """
    return {
        # Xarray keys a dataset by Hashable; every name this package writes is
        # a string, and the encoding map must be keyed by one.
        str(name): {"zlib": True, "complevel": complevel}
        for name, array in ds.variables.items()
        if array.dtype.kind not in "OUS" and array.ndim > 0
    }


def export_dataset(
    ds: xr.Dataset,
    destination: str | Path,
    formats: Iterable[str] = ("netcdf",),
    *,
    stem: str = "track",
) -> dict[str, Path]:
    """Export a canonical dataset to NetCDF, Zarr v2, and/or track-only CSV.

    CSV includes only variables whose dimensions are exactly ``(time,)`` and is
    therefore intentionally lossy. NetCDF and Zarr retain every dimension.

    Each file is written as ``<stem>.<ext>`` in ``destination``. A campaign
    names its own, through :func:`yacht_co2.naming.output_stem`; the default
    suits a caller exporting one dataset to a folder of its own.
    """
    validate_dataset(ds)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Path] = {}
    for requested in formats:
        fmt = requested.lower().replace(".nc", "netcdf")
        if fmt in {"netcdf", "nc"}:
            path = destination / f"{stem}.nc"
            ds.to_netcdf(path, engine="h5netcdf", encoding=netcdf_encoding(ds))
            artifacts["netcdf"] = path
        elif fmt in {"zarr", "zarr2"}:
            path = destination / f"{stem}.zarr"
            ds.to_zarr(path, mode="w", consolidated=True, zarr_format=2)
            artifacts["zarr"] = path
        elif fmt == "csv":
            path = destination / f"{stem}.csv"
            names = [name for name, array in ds.data_vars.items() if array.dims == ("time",)]
            ds[names].to_dataframe().reset_index().to_csv(path, index=False)
            artifacts["csv"] = path
        else:
            raise ValueError(f"unsupported export format: {requested}")
    logger.success("Wrote {} dataset artifacts to {}", len(artifacts), destination)
    return artifacts


def datasets_identical(left: str | Path, right: str | Path) -> bool:
    """Return whether two serialized xarray datasets are identical."""

    def open_one(path: str | Path) -> xr.Dataset:
        path = Path(path)
        return xr.open_zarr(path) if path.suffix == ".zarr" else xr.open_dataset(path)

    try:
        xr.testing.assert_identical(open_one(left), open_one(right))
    except AssertionError:
        return False
    return True
