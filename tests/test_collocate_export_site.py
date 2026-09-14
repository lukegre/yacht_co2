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
    ds["value"].attrs["units"] = "uatm"
    ds["raw_watertemp"] = ("time", [12.0, 13.0])
    ds["raw_salinity"] = ("time", [34.8, 34.9])
    ds["raw_chl_a"] = ("time", [0.7, 0.8])
    ds["dissolved_oxygen"] = xr.DataArray(
        [250.0, 251.0], dims=("time",), attrs={"units": "umol kg-1"}
    )
    paths = export_dataset(ds, tmp_path, ["netcdf", "zarr", "csv"])
    assert all(path.exists() for path in paths.values())
    html = build_site(
        ds,
        tmp_path / "single.html",
        single_file=True,
        qc_config={
            "analysis_phases": [5],
            "minimum_water_flow": 0.1,
            "minimum_gas_flow": 0.1,
        },
    )
    rendered = html.read_text()
    assert "Observation chart" in rendered
    assert 'aria-label="Add time series"' in rendered
    assert 'aria-label="Chart x-axis"' in rendered
    assert "Latitude" in rendered
    assert "Longitude" in rendered
    assert "dragmode:'zoom'" in rendered
    assert "width:2.8" in rendered
    assert "observations in chart window" in rendered
    assert "µatm" in rendered
    assert "spectralR" in rendered
    assert "bindTooltip" in rendered
    assert "QC-good means every applicable check passes" in rendered
    assert "aria-describedby=qc-help" in rendered
    assert "Water flow" in rendered
    assert "≥ 0.1" in rendered
    assert "-2.5 to 45 °C" in rendered
    assert "defaultChartVariables=['fco2_seawater','raw_watertemp']" in rendered
    assert "rgba(70,91,99,.52)" in rendered
    assert "dash:'dot'" in rendered
    assert "variable_meta" in rendered
    assert "Water temperature" in rendered
    assert "Salinity" in rendered
    assert "Chlorophyll a" in rendered
    assert "Dissolved oxygen" in rendered
    assert "yaxis2" in rendered
    assert 'type=range' not in rendered
    assert "NaN" not in rendered
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
