from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from yacht_co2.errors import ManifestError, ProviderError
from yacht_co2.manifest import load_manifest
from yacht_co2.pipeline import Pipeline
from yacht_co2.providers import (
    CMEMSProvider,
    ERA5Provider,
    LocalFileProvider,
    NOAAMBLProvider,
    ProductRequest,
    fetch_products,
)


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def fetch(self, request: ProductRequest, destination: Path) -> xr.Dataset:
        self.calls += 1
        return xr.Dataset(
            {"wind_speed": (("time", "lat", "lon"), [[[5.0]]])},
            coords={"time": [np.datetime64("2023-01-01")], "lat": [1.0], "lon": [2.0]},
        )


def canonical_track():
    return xr.Dataset(
        {
            "lat": ("time", [1.0]),
            "lon": ("time", [2.0]),
            "source_file": ("time", ["a.log"]),
            "qc_flag": ("time", np.zeros(1, dtype="uint16")),
        },
        coords={"time": [np.datetime64("2023-01-01")]},
    )


def test_manifest_errors_and_digest(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("[]")
    with pytest.raises(ManifestError, match="root"):
        load_manifest(bad)
    good = tmp_path / "good.yaml"
    good.write_text("expedition: {name: Test}\ninputs: {logs: '*.log'}\n")
    assert load_manifest(good).digest == load_manifest(good).digest


def test_provider_cache_and_optional_failure(tmp_path):
    spec = {
        "name": "wind",
        "provider": "fake",
        "product_id": "x",
        "variables": ["wind_speed"],
    }
    fake = FakeProvider()
    products, status = fetch_products(
        canonical_track(), [spec], cache_dir=tmp_path, providers={"fake": fake}
    )
    assert products["wind"].wind_speed.item() == 5
    assert status[0]["status"] == "fetched"
    fetch_products(canonical_track(), [spec], cache_dir=tmp_path, providers={"fake": fake})
    assert fake.calls == 1
    optional = {**spec, "provider": "unknown", "required": False}
    _, status = fetch_products(canonical_track(), [optional], cache_dir=tmp_path)
    assert status[0]["status"] == "failed"
    with pytest.raises(ProviderError):
        fetch_products(canonical_track(), [{**optional, "required": True}], cache_dir=tmp_path)


def test_local_and_noaa_adapters(tmp_path, monkeypatch):
    grid = xr.Dataset(
        {"sst": (("time", "lat", "lon"), [[[20.0]]])},
        coords={"time": [np.datetime64("2023-01-01")], "lat": [1.0], "lon": [2.0]},
    )
    local_path = tmp_path / "local.nc"
    grid.to_netcdf(local_path)
    request = ProductRequest("local", "local", ("sst",), "2022-12-31", "2023-01-02", 1, 3, 0, 2)
    assert LocalFileProvider(local_path).fetch(request, tmp_path).sst.item() == 20
    assert request.cache_key == request.cache_key

    def fake_download(url, output):
        Path(output).write_text("2022 12 0 417.0\n2023 1 0 418.0\n")

    monkeypatch.setattr("urllib.request.urlretrieve", fake_download)
    noaa_request = ProductRequest(
        "noaa_mbl", "global", ("xco2_air",), "2023-01-01", "2023-02-01", -180, 180, -90, 90
    )
    assert NOAAMBLProvider().fetch(noaa_request, tmp_path / "noaa").xco2_air.item() == 418


def test_optional_provider_dependency_errors(tmp_path, monkeypatch):
    request = ProductRequest("x", "x", ("x",), "2023-01-01", "2023-01-02", 0, 1, 0, 1)
    real_import = __import__

    def missing(name, *args, **kwargs):
        if name == "copernicusmarine":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", missing)
    with pytest.raises(ProviderError, match="cmems"):
        CMEMSProvider().fetch(request, tmp_path)


def test_weatherbench_era5_zarr_subset_aliases_and_coverage(tmp_path):
    store = tmp_path / "weatherbench.zarr"
    time = np.array(["2022-12-31T18", "2023-01-01T00", "2023-01-01T06"], dtype="datetime64[ns]")
    shape = (3, 2, 4)
    xr.Dataset(
        {
            "10m_u_component_of_wind": (("time", "latitude", "longitude"), np.ones(shape)),
            "10m_v_component_of_wind": (("time", "latitude", "longitude"), np.ones(shape) * 2),
        },
        coords={"time": time, "latitude": [49.0, 50.0], "longitude": [0.0, 1.0, 358.0, 359.0]},
    ).to_zarr(store, zarr_format=2)
    provider = ERA5Provider(store)
    request = ProductRequest(
        "era5", "", ("u10", "v10"), "2023-01-01", "2023-01-01T06", -2, 1, 49, 50
    )
    result = provider.fetch(request, tmp_path)
    assert {"u10", "v10"}.issubset(result)
    assert set(result.longitude.values) == {0, 1, 358, 359}
    outside = ProductRequest("era5", "", ("u10",), "2023-01-01", "2023-01-02", -2, 1, 49, 50)
    with pytest.raises(ProviderError, match="outside archive coverage"):
        provider.fetch(outside, tmp_path)


def test_pipeline_processes_fixture(tmp_path):
    log = tmp_path / "one.log"
    log.write_text(
        "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,"
        "AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"
        "@DATA,2023-01-01,00:00:00,0,400,10,20,1013.25,5000,00200,1,1,20,35,0,5\n"
    )
    manifest = tmp_path / "expedition.yaml"
    manifest.write_text(
        "expedition: {name: Test}\ninputs: {logs: '*.log', timezone: UTC}\n"
        "calibration: {method: instrument}\nqc: {analysis_phases: [5]}\n"
        "outputs: {directory: out, formats: [netcdf]}\n"
    )
    result = Pipeline(manifest).run(enrich=False, site=True)
    assert result.dataset.pco2_seawater.item() == pytest.approx(400)
    assert result.artifacts["netcdf"].exists()
    assert result.artifacts["site"].exists()
