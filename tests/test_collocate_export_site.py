import numpy as np
import pytest
import xarray as xr

from yacht_co2.collocate import collocate_track, resolve_air_co2
from yacht_co2.export import datasets_identical, export_dataset
from yacht_co2.schema import validate_dataset
from yacht_co2.site import build_site


def track():
    time = np.array(["2023-01-01T00", "2023-01-01T02"], dtype="datetime64[ns]")
    return xr.Dataset(
        {
            "lat": ("time", [0.1, 0.9]),
            "lon": ("time", [10.1, 10.9]),
            "source_file": ("time", ["a", "a"]),
            "qc_flag": ("time", np.zeros(2, dtype="uint16")),
        },
        coords={"time": time},
    )


def test_collocation_squares_wind_before_selection():
    product = xr.Dataset(
        {
            "wind_speed": (
                ("time", "lat", "lon"),
                np.array([[[2.0, 3.0], [4.0, 5.0]], [[3.0, 4.0], [5.0, 6.0]]]),
            )
        },
        coords={
            "time": np.array(["2023-01-01T00", "2023-01-01T02"], dtype="datetime64[ns]"),
            "lat": [0.0, 1.0],
            "lon": [10.0, 11.0],
        },
    )
    ds = collocate_track(track(), product, variables=["wind_speed", "wind_speed_squared"])
    assert list(ds.wind_speed.values) == [2, 6]
    assert list(ds.wind_speed_squared.values) == [4, 36]


def test_collocation_derives_weatherbench_wind_components():
    product = xr.Dataset(
        {
            "u10": (("time", "lat", "lon"), [[[3.0]], [[5.0]]]),
            "v10": (("time", "lat", "lon"), [[[4.0]], [[12.0]]]),
        },
        coords={
            "time": np.array(["2023-01-01T00", "2023-01-01T02"], dtype="datetime64[ns]"),
            "lat": [0.0],
            "lon": [10.0],
        },
    )
    source = track().assign(lat=("time", [0.0, 0.0]), lon=("time", [10.0, 10.0]))
    result = collocate_track(source, product, variables=["u10", "v10"])
    assert list(result.wind_speed.values) == [5.0, 13.0]
    assert list(result.wind_speed_squared.values) == [25.0, 169.0]


def test_air_priority():
    ds = track()
    obs = xr.Dataset({"xco2_air": ("time", [410.0, 411.0])}, coords={"time": ds.time})
    out = resolve_air_co2(ds, observations=obs)
    assert list(out.air_co2_source.values) == ["observations", "observations"]


def test_exports_and_site(tmp_path):
    ds = track()
    ds["value"] = ("time", [1.0, np.nan])
    paths = export_dataset(ds, tmp_path, ["netcdf", "zarr", "csv"])
    assert all(path.exists() for path in paths.values())
    html = build_site(ds, tmp_path / "single.html", single_file=True)
    assert "Time scrubber" in html.read_text()
    assert "NaN" not in html.read_text()
    assert datasets_identical(paths["netcdf"], paths["zarr"])
    with pytest.raises(ValueError, match="unsupported"):
        export_dataset(ds, tmp_path, ["parquet"])


def test_schema_and_collocation_tolerance_errors():
    with pytest.raises(ValueError, match="time"):
        validate_dataset(xr.Dataset())
    product = xr.Dataset(
        {"x": (("time", "lat", "lon"), [[[1.0]]])},
        coords={"time": [np.datetime64("2024-01-01")], "lat": [0.0], "lon": [10.0]},
    )
    out = collocate_track(track(), product, time_tolerance="1h")
    assert np.isnan(out.x).all()
    assert np.all(out.qc_flag.values & 256)
