import json

import h5py
import numpy as np
import pytest
import xarray as xr

from yacht_co2.collocate import collocate_track, resolve_air_co2
from yacht_co2.export import datasets_identical, export_dataset
from yacht_co2.naming import output_name, output_stem
from yacht_co2.schema import validate_dataset
from yacht_co2.site import build_site, parse_size, site_filename


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


def test_netcdf_export_is_compressed(tmp_path):
    ds = track()
    # A long, highly compressible series: the gain has to be visible in bytes.
    ds = ds.isel(time=0, drop=False).expand_dims(time=1)
    ds = xr.concat([ds] * 500, dim="time")
    ds["time"] = ("time", np.arange("2023-01-01", "2023-01-01T08:20", dtype="datetime64[m]")[:500])

    path = export_dataset(ds, tmp_path, ["netcdf"])["netcdf"]
    plain = tmp_path / "plain.nc"
    ds.to_netcdf(plain, engine="h5netcdf")

    assert path.stat().st_size < plain.stat().st_size
    # Every numeric variable and coordinate carries the deflate filter.
    with h5py.File(path) as handle:
        assert handle["lat"].compression == "gzip"
        assert handle["time"].compression == "gzip"
        # Strings cannot be deflated, so they are written as they are.
        assert handle["source_file"].compression is None
    assert datasets_identical(path, plain)


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
    # The map colour limits are clipped to the central 95% of QC-good values.
    assert "MAP_CLIP=[.025,.975]" in rendered
    assert "percentileRange(scaleValues,MAP_CLIP[0],MAP_CLIP[1])" in rendered
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
    assert "type=range" not in rendered
    assert "NaN" not in rendered
    assert datasets_identical(paths["netcdf"], paths["zarr"])
    with pytest.raises(ValueError, match="unsupported"):
        export_dataset(ds, tmp_path, ["parquet"])


def phase_track(count=40):
    """A track alternating between the seawater and air sampling phases."""
    time = np.datetime64("2023-01-01", "m") + np.arange(count)
    phase = np.where(np.arange(count) % 4 < 3, 5.0, 22.0)
    return xr.Dataset(
        {
            "lat": ("time", np.linspace(0, 1, count)),
            "lon": ("time", np.linspace(10, 11, count)),
            "fco2_seawater": ("time", np.linspace(380, 420, count), {"units": "uatm"}),
            "raw_watertemp": ("time", np.linspace(12, 15, count)),
            "raw_salinity": ("time", np.linspace(34, 35, count)),
            "raw_sampling_phase": ("time", phase),
            # The air phase is outside qc.analysis_phases, so it is flagged.
            "qc_flag": ("time", np.where(phase == 5, 0, 8).astype("uint16")),
        },
        coords={"time": time.astype("datetime64[ns]")},
    )


def model_of(path):
    text = path.read_text()
    return json.loads(text.split("window.YACHT_DATA=")[1].split(";window.YACHT_REPORT")[0])


def test_the_page_carries_the_sampling_phase_and_names_it(tmp_path):
    """Phase travels whatever else is dropped, so the page can be filtered by it."""
    path = build_site(
        phase_track(),
        tmp_path / "phase.html",
        variables=["fco2_seawater"],
        phase_config={"analysis": [5], "air": [22]},
    )
    model = model_of(path)

    assert sorted(set(model["phase"])) == [5, 22]
    assert model["phase_meta"] == {"5": "Seawater", "22": "Air"}
    # The picker filters the map and the charts alongside the QC toggle, not
    # instead of it, so a flagged phase is still viewable with QC off.
    rendered = path.read_text()
    assert 'aria-label="Sampling phase to display"' in rendered
    assert "function phaseOk(i)" in rendered
    assert "function included(i)" in rendered
    assert "eligibleIndices(){return S.time.map((_,i)=>i).filter(included)}" in rendered


def test_site_variables_choose_what_the_page_stores(tmp_path):
    """Only the requested columns travel, in the order asked for."""
    path = build_site(
        phase_track(),
        tmp_path / "chosen.html",
        variables=["raw_salinity", "fco2_seawater", "not_measured"],
    )
    model = model_of(path)

    assert model["variables"] == ["raw_salinity", "fco2_seawater"]
    assert "raw_watertemp" not in model["data"]
    # Time, position, QC and phase are what the page is drawn from, so they stay.
    assert set(model) >= {"time", "lat", "lon", "qc", "phase"}
    # A name the track does not hold is reported and skipped, not fatal.
    assert "not_measured" not in model["variables"]
    # Every numeric column travels when nothing is asked for.
    everything = model_of(build_site(phase_track(), tmp_path / "all.html"))
    assert "raw_watertemp" in everything["variables"]


def test_a_page_budget_may_be_written_as_a_size(tmp_path):
    """max_bytes takes '120 kB' as readily as a number, and the page obeys it."""
    assert parse_size("10 MB") == 10_000_000
    assert parse_size("8 MiB") == 8 * 2**20
    assert parse_size(2048) == 2048
    with pytest.raises(ValueError, match="not a size"):
        parse_size("ten megabytes")

    ds = phase_track(4000)
    big = build_site(ds, tmp_path / "big.html", max_bytes="4 MB")
    small = build_site(ds, tmp_path / "small.html", max_bytes="120 kB")

    assert small.stat().st_size <= 120_000
    assert len(model_of(small)["time"]) < len(model_of(big)["time"]) == 4000


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


def test_every_artifact_is_named_for_its_campaign():
    """One rule names them all, so products from many campaigns never collide."""
    # A hyphen separates the fields; within a field it becomes an underscore.
    assert output_name("Fastnet Race", "2023-07-24", "track", "nc") == (
        "yacht_co2-fastnet_race-2023_07_24-track.nc"
    )
    assert output_name("Fastnet Race", "2023-07-24", "report", "json") == (
        "yacht_co2-fastnet_race-2023_07_24-report.json"
    )
    # A provider name carrying a dot stays one field of the name.
    assert output_name("Fastnet", "2023-06", "product-cmems.glorys", "nc") == (
        "yacht_co2-fastnet-2023_06-product-cmems_glorys.nc"
    )
    # The hosted site bundle is a folder, so it is named without an extension.
    assert output_stem("Fastnet", "2023-06", "site") == "yacht_co2-fastnet-2023_06-site"
    assert site_filename("Fastnet", "2023-06") == "yacht_co2-fastnet-2023_06-site.html"
    with pytest.raises(ValueError, match="cannot both be empty"):
        output_name("", "", "track", "nc")


def test_export_names_every_format_from_one_stem(tmp_path):
    paths = export_dataset(track(), tmp_path, ["netcdf", "csv"], stem="yacht_co2-fastnet-track")

    assert paths["netcdf"].name == "yacht_co2-fastnet-track.nc"
    assert paths["csv"].name == "yacht_co2-fastnet-track.csv"
