"""Environmental product providers and content-addressed caching."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import xarray as xr
from loguru import logger

from .errors import ProviderError
from .export import netcdf_encoding


@dataclass(frozen=True)
class ProductRequest:
    """Provider-independent spatiotemporal request."""

    provider: str
    product_id: str
    variables: tuple[str, ...]
    start: str
    end: str
    west: float
    east: float
    south: float
    north: float
    version: str = "latest"

    @property
    def cache_key(self) -> str:
        value = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(value.encode()).hexdigest()[:24]


class ProductProvider(Protocol):
    """Protocol implemented by remote and local gridded-data adapters."""

    name: str

    def fetch(self, request: ProductRequest, destination: Path) -> xr.Dataset: ...


class LocalFileProvider:
    """Open a local NetCDF/Zarr product and subset it to the request."""

    name = "local"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self, request: ProductRequest, destination: Path) -> xr.Dataset:
        del destination
        ds = xr.open_zarr(self.path) if self.path.suffix == ".zarr" else xr.open_dataset(self.path)
        selection: dict[str, Any] = {}
        if "time" in ds.coords:
            selection["time"] = slice(request.start, request.end)
        if "lat" in ds.coords:
            selection["lat"] = slice(request.south, request.north)
        if "latitude" in ds.coords:
            selection["latitude"] = slice(request.south, request.north)
        if "lon" in ds.coords:
            selection["lon"] = slice(request.west, request.east)
        if "longitude" in ds.coords:
            selection["longitude"] = slice(request.west, request.east)
        return ds.sel(selection)[list(request.variables)].load()


class CMEMSProvider:
    """Copernicus Marine Toolbox adapter (credentials use its normal config)."""

    name = "cmems"

    def fetch(self, request: ProductRequest, destination: Path) -> xr.Dataset:
        try:
            import copernicusmarine
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ProviderError("install yacht-co2[cmems] to fetch CMEMS products") from exc
        output = destination / "product.nc"
        output.parent.mkdir(parents=True, exist_ok=True)
        copernicusmarine.subset(
            dataset_id=request.product_id,
            variables=list(request.variables),
            minimum_longitude=request.west,
            maximum_longitude=request.east,
            minimum_latitude=request.south,
            maximum_latitude=request.north,
            start_datetime=request.start,
            end_datetime=request.end,
            output_filename=output.name,
            output_directory=str(output.parent),
            force_download=True,
        )
        return xr.open_dataset(output).load()


class ERA5Provider:
    """Read public WeatherBench 2 ERA5 data directly from its cloud Zarr store."""

    name = "era5"
    DEFAULT_STORE = (
        "gs://weatherbench2/datasets/era5/"
        "1959-2023_01_10-wb13-6h-1440x721_with_derived_variables.zarr"
    )
    VARIABLE_NAMES = {
        "u10": "10m_u_component_of_wind",
        "v10": "10m_v_component_of_wind",
        "wind_speed": "10m_wind_speed",
    }

    def __init__(self, store_url: str | Path | None = None):
        self.store_url = str(store_url) if store_url is not None else None

    def fetch(self, request: ProductRequest, destination: Path) -> xr.Dataset:
        del destination
        store = self.store_url or request.product_id or self.DEFAULT_STORE
        storage_options = {"token": "anon"} if store.startswith("gs://") else None
        try:
            ds = xr.open_zarr(store, chunks=None, storage_options=storage_options)
        except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - optional dependency
            raise ProviderError("install yacht-co2[era5] to read WeatherBench Zarr") from exc
        source_variables = [self.VARIABLE_NAMES.get(name, name) for name in request.variables]
        missing = sorted(set(source_variables) - set(ds.data_vars))
        if missing:
            raise ProviderError(f"WeatherBench ERA5 variables not found: {', '.join(missing)}")
        available_start = pd.Timestamp(ds.time.min().item())
        available_end = pd.Timestamp(ds.time.max().item())
        if (
            pd.Timestamp(request.start) < available_start
            or pd.Timestamp(request.end) > available_end
        ):
            raise ProviderError(
                "WeatherBench ERA5 request is outside archive coverage "
                f"({available_start.isoformat()} to {available_end.isoformat()})"
            )
        subset = ds[source_variables].sel(time=slice(request.start, request.end))
        subset = _spatial_subset(subset, request)
        if not subset.sizes.get("time", 0) or not subset.sizes.get("latitude", 0):
            raise ProviderError("WeatherBench ERA5 request produced an empty subset")
        subset = subset.load()
        aliases = {
            source: alias for alias, source in self.VARIABLE_NAMES.items() if source in subset
        }
        return subset.rename(aliases)


def _spatial_subset(ds: xr.Dataset, request: ProductRequest) -> xr.Dataset:
    """Subset WeatherBench's increasing latitude and 0–360 longitude grid."""
    latitude = ds.latitude
    lat_slice = (
        slice(request.south, request.north)
        if float(latitude[0]) <= float(latitude[-1])
        else slice(request.north, request.south)
    )
    ds = ds.sel(latitude=lat_slice)
    west = request.west % 360.0
    east = request.east % 360.0
    if west <= east and request.east - request.west < 360:
        return ds.sel(longitude=slice(west, east))
    western = ds.sel(longitude=slice(west, None))
    eastern = ds.sel(longitude=slice(None, east))
    return xr.concat([western, eastern], dim="longitude")


class NOAAMBLProvider:
    """NOAA GML marine-boundary-layer reference surface text adapter."""

    name = "noaa_mbl"
    DEFAULT_URL = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_gl.txt"

    def __init__(self, url: str | None = None):
        self.url = url or self.DEFAULT_URL

    def fetch(self, request: ProductRequest, destination: Path) -> xr.Dataset:
        output = destination / "co2_mm_gl.txt"
        output.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(self.url, output)  # noqa: S310
        table = pd.read_csv(output, sep=r"\s+", comment="#", header=None)
        if table.shape[1] < 4:
            raise ProviderError("unexpected NOAA MBL text format")
        time = pd.to_datetime(dict(year=table.iloc[:, 0], month=table.iloc[:, 1], day=15))
        values = pd.to_numeric(table.iloc[:, 3], errors="coerce")
        ds = xr.Dataset({"xco2_air": ("time", values)}, coords={"time": time})
        return ds.sel(time=slice(request.start, request.end))


def request_from_track(spec: dict[str, Any], track: xr.Dataset) -> ProductRequest:
    """Create a padded request covering the complete campaign track."""
    pad_days = float(spec.get("time_padding_days", 1))
    pad_deg = float(spec.get("spatial_padding_degrees", 1))
    valid = track[["lat", "lon"]].where((track.qc_flag & 6) == 0)
    start = pd.Timestamp(track.time.min().item()) - pd.Timedelta(days=pad_days)
    end = pd.Timestamp(track.time.max().item()) + pd.Timedelta(days=pad_days)
    return ProductRequest(
        provider=str(spec["provider"]),
        product_id=str(spec.get("product_id", "")),
        variables=tuple(spec["variables"]),
        start=start.isoformat(),
        end=end.isoformat(),
        west=float(valid.lon.min()) - pad_deg,
        east=float(valid.lon.max()) + pad_deg,
        south=float(valid.lat.min()) - pad_deg,
        north=float(valid.lat.max()) + pad_deg,
        version=str(spec.get("version", "latest")),
    )


def fetch_products(
    track: xr.Dataset,
    specs: list[dict[str, Any]],
    *,
    cache_dir: str | Path,
    providers: dict[str, ProductProvider] | None = None,
) -> tuple[dict[str, xr.Dataset], list[dict[str, str]]]:
    """Fetch requested products, returning datasets and structured statuses."""
    providers = dict(providers or {})
    providers.setdefault("cmems", CMEMSProvider())
    providers.setdefault("era5", ERA5Provider())
    providers.setdefault("noaa_mbl", NOAAMBLProvider())
    cache_dir = Path(cache_dir)
    products: dict[str, xr.Dataset] = {}
    statuses: list[dict[str, str]] = []
    for spec in specs:
        name = str(spec.get("name", spec.get("product_id", spec["provider"])))
        request = request_from_track(spec, track)
        folder = cache_dir / request.provider / request.cache_key
        cached = folder / "cache.nc"
        try:
            if cached.is_file():
                product = xr.open_dataset(cached).load()
                state = "cached"
            else:
                provider = providers.get(request.provider)
                if provider is None and request.provider == "local":
                    provider = LocalFileProvider(spec["path"])
                if provider is None:
                    raise ProviderError(f"unknown provider: {request.provider}")
                product = provider.fetch(request, folder)
                folder.mkdir(parents=True, exist_ok=True)
                product.to_netcdf(cached, engine="h5netcdf", encoding=netcdf_encoding(product))
                (folder / "request.json").write_text(json.dumps(asdict(request), indent=2))
                state = "fetched"
            product.attrs.update(provider=request.provider, request_cache_key=request.cache_key)
            products[name] = product
            statuses.append({"name": name, "status": state, "message": ""})
            logger.success("Product {} {}", name, state)
        except Exception as exc:
            statuses.append({"name": name, "status": "failed", "message": str(exc)})
            if bool(spec.get("required", True)):
                raise ProviderError(f"required product {name!r} failed: {exc}") from exc
            logger.warning("Optional product {} failed: {}", name, exc)
    return products, statuses
