"""Lossless scientific exports and a documented flattened CSV view."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import xarray as xr
from loguru import logger

from .schema import validate_dataset


def export_dataset(
    ds: xr.Dataset,
    destination: str | Path,
    formats: Iterable[str] = ("netcdf",),
) -> dict[str, Path]:
    """Export a canonical dataset to NetCDF, Zarr v2, and/or track-only CSV.

    CSV includes only variables whose dimensions are exactly ``(time,)`` and is
    therefore intentionally lossy. NetCDF and Zarr retain every dimension.
    """
    validate_dataset(ds)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Path] = {}
    for requested in formats:
        fmt = requested.lower().replace(".nc", "netcdf")
        if fmt in {"netcdf", "nc"}:
            path = destination / "track.nc"
            encoding = {
                name: {"zlib": True, "complevel": 4}
                for name, array in ds.data_vars.items()
                if array.dtype.kind not in "OUS"
            }
            ds.to_netcdf(path, engine="h5netcdf", encoding=encoding)
            artifacts["netcdf"] = path
        elif fmt in {"zarr", "zarr2"}:
            path = destination / "track.zarr"
            ds.to_zarr(path, mode="w", consolidated=True, zarr_format=2)
            artifacts["zarr"] = path
        elif fmt == "csv":
            path = destination / "track.csv"
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
