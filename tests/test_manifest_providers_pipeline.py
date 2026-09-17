from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml
from loguru import logger

from yacht_co2.errors import ManifestError, ProviderError
from yacht_co2.manifest import build_manifest, load_manifest
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
    good.write_text("campaign: {name: Test}\ninputs: {logs: '*.log'}\n")
    assert load_manifest(good).digest == load_manifest(good).digest


def test_build_manifest_uses_zenodo_name_and_processing_defaults(tmp_path):
    folder = tmp_path / "campaign"
    folder.mkdir()
    zenodo = folder / "zenodo.yaml"
    zenodo.write_text(
        "campaign: Défi Azimut (solo)\ncampaign_date: 2022-09\ndoi: 10.5281/zenodo.12345\n"
    )

    messages = []
    handler = logger.add(messages.append, format="{message}")
    try:
        path = build_manifest(zenodo)
    finally:
        logger.remove(handler)

    document = yaml.safe_load(path.read_text())
    assert path == folder / "manifest.yaml"
    assert document["campaign"] == {
        "id": "campaign",
        "name": "Défi Azimut (solo)",
        "date": "2022-09",
    }
    assert document["inputs"] == {
        "repository": "10.5281/zenodo.12345",
        "logs": "./*.log",
        "timezone": "UTC",
    }
    assert document["calibration"]["method"] == "instrument"
    assert document["equilibrator"]["water_temperature"] == "watertemp"
    assert document["outputs"]["formats"] == ["netcdf"]
    assert load_manifest(path).name == "Défi Azimut (solo)"
    assert any("Loading manifest defaults" in message for message in messages)
    assert any("Resolved campaign id 'campaign'" in message for message in messages)
    assert any("Built campaign manifest" in message for message in messages)


def test_build_manifest_accepts_explicit_zenodo_title(tmp_path):
    zenodo = tmp_path / "zenodo.yaml"
    zenodo.write_text("title: Custom campaign\nslug: custom-campaign\ndoi: 10.5281/zenodo.12345\n")

    path = build_manifest(zenodo)

    assert yaml.safe_load(path.read_text())["campaign"] == {
        "id": "custom-campaign",
        "name": "Custom campaign",
    }


def test_build_manifest_requires_a_zenodo_repository(tmp_path):
    zenodo = tmp_path / "zenodo.yaml"
    zenodo.write_text("campaign: Unpublished campaign\n")

    with pytest.raises(ManifestError, match="needs doi.*inputs.repository"):
        build_manifest(zenodo)


def test_built_manifest_fetches_default_logs_from_zenodo(tmp_path, monkeypatch):
    zenodo = tmp_path / "zenodo.yaml"
    zenodo.write_text(
        "campaign: Remote campaign\ncampaign_date: 2023-06\ndoi: 10.5281/zenodo.12345\n"
    )
    manifest = build_manifest(zenodo)
    log = tmp_path / "remote.log"
    log.write_text("@NAME,DATE,TIME,Latitude,Longitude\n@DATA,2023-01-01,12:00:00,5000,00100\n")
    call = {}

    def fake_fetch(repository, pattern, cache):
        call.update(repository=repository, pattern=pattern, cache=cache)
        return [log]

    monkeypatch.setattr("yacht_co2.pipeline.fetch_zenodo_logs", fake_fetch)

    result = Pipeline(manifest).ingest()

    assert result.sizes["time"] == 1
    assert call == {
        "repository": "10.5281/zenodo.12345",
        "pattern": "./*.log",
        "cache": (tmp_path / "../.cache").resolve(),
    }


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


def test_pipeline_processes_fixture(tmp_path, monkeypatch):
    log = tmp_path / "one.log"
    log.write_text(
        "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,"
        "AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"
        "@DATA,2023-01-01,00:00:00,0,400,10,20,1013.25,5000,00200,1,1,20,35,0,5\n"
    )
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "campaign: {name: Test}\ninputs: {logs: '*.log', timezone: UTC}\n"
        "calibration: {method: instrument}\nphases: {analysis: [5]}\n"
        "outputs: {directory: out, formats: [netcdf]}\n"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = Pipeline(manifest).run(enrich=False, site=True)
    assert result.dataset.pco2_seawater.item() == pytest.approx(400)
    assert result.artifacts["netcdf"].parent == tmp_path / "out"
    assert result.artifacts["netcdf"].exists()
    assert result.artifacts["site"].exists()


def test_local_product_and_cache_paths_are_relative_to_manifest(tmp_path, monkeypatch):
    manifest_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    manifest_dir.mkdir()
    data_dir.mkdir()
    xr.Dataset(
        {"sst": (("time", "lat", "lon"), [[[20.0]]])},
        coords={"time": [np.datetime64("2023-01-01")], "lat": [1.0], "lon": [2.0]},
    ).to_netcdf(data_dir / "local.nc")
    manifest = manifest_dir / "manifest.yaml"
    manifest.write_text(
        "campaign: {name: Test}\n"
        "inputs: {logs: '*.log'}\n"
        "products:\n"
        "  - {name: sst, provider: local, path: ../data/local.nc, variables: [sst]}\n"
        "outputs: {cache: ../cache}\n"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    enriched, products, statuses = Pipeline(manifest).enrich(canonical_track())

    assert enriched.sst.item() == 20
    assert products["sst"].sst.item() == 20
    assert statuses[0]["status"] == "fetched"
    assert next((tmp_path / "cache").rglob("cache.nc")).is_file()
