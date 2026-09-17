"""End-to-end orchestration with explicit intermediate results."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import xarray as xr
from loguru import logger

from .collocate import collocate_track, resolve_air_co2
from .export import export_dataset, netcdf_encoding
from .ingest import fetch_zenodo_logs, read_campaign
from .manifest import CampaignManifest, load_manifest
from .naming import output_name, output_stem
from .project import load_platform
from .providers import ProductProvider, fetch_products
from .qc import apply_qc
from .report import summarise, write_report
from .science import calibrate_co2, derive_fco2, derive_flux, derive_pco2
from .site import build_site, site_filename
from .video import render_video


@dataclass
class RunResult:
    """Dataset and artifact inventory produced by a pipeline run."""

    dataset: xr.Dataset
    products: dict[str, xr.Dataset] = field(default_factory=dict)
    artifacts: dict[str, Path] = field(default_factory=dict)
    product_status: list[dict[str, str]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _code_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class Pipeline:
    """Reproducible campaign processor configured by a YAML manifest."""

    def __init__(
        self,
        manifest: str | Path | CampaignManifest,
        *,
        providers: dict[str, ProductProvider] | None = None,
    ):
        self.manifest = (
            load_manifest(manifest) if not isinstance(manifest, CampaignManifest) else manifest
        )
        self.providers = providers

    def ingest(self) -> xr.Dataset:
        """Read all manifest-selected source logs."""
        logs = str(self.manifest.inputs["logs"])
        repository = self.manifest.inputs.get("repository")
        if repository:
            cache = self.manifest.resolve_path(
                self.manifest.outputs.get("cache", ".cache/yacht-co2")
            )
            source: str | Path | list[Path] = fetch_zenodo_logs(str(repository), logs, cache)
        else:
            source = self.manifest.resolve_path(logs)
        return read_campaign(source, timezone=str(self.manifest.inputs.get("timezone", "UTC")))

    def process(self, ds: xr.Dataset) -> xr.Dataset:
        """Apply local QC, calibration, pCO2 and fCO2 processing."""
        ds = apply_qc(ds, self.manifest.qc)
        ds = calibrate_co2(ds, self.manifest.calibration)
        ds = derive_pco2(ds, self.manifest.equilibrator)
        return derive_fco2(ds)

    def enrich(
        self, ds: xr.Dataset
    ) -> tuple[xr.Dataset, dict[str, xr.Dataset], list[dict[str, str]]]:
        """Fetch configured products, collocate them, and resolve air CO2."""
        cache_path = self.manifest.resolve_path(
            self.manifest.outputs.get("cache", ".cache/yacht-co2")
        )
        specs = [dict(spec) for spec in self.manifest.products]
        for spec in specs:
            if spec.get("provider") == "local" and "path" in spec:
                spec["path"] = self.manifest.resolve_path(spec["path"])
        products, statuses = fetch_products(
            ds, specs, cache_dir=cache_path, providers=self.providers
        )
        enriched = ds
        for spec in specs:
            name = str(spec.get("name", spec.get("product_id", spec["provider"])))
            if name not in products or not spec.get("collocate", True):
                continue
            enriched = collocate_track(
                enriched,
                products[name],
                variables=spec.get("variables"),
                time_tolerance=spec.get("time_tolerance", "12h"),
                spatial_tolerance_degrees=spec.get("spatial_tolerance_degrees"),
                prefix=str(spec.get("prefix", "")),
            )
        observation_product = products.get(
            str(self.manifest.atmosphere.get("observations_product", ""))
        )
        noaa_product = products.get(str(self.manifest.atmosphere.get("noaa_product", "")))
        enriched = resolve_air_co2(
            enriched, observation_product, noaa_product, self.manifest.atmosphere
        )
        if {"fco2_seawater", "fco2_air"}.issubset(enriched) and (
            "wind_speed" in enriched or "wind_speed_squared" in enriched
        ):
            enriched = derive_flux(enriched, self.manifest.flux)
        return enriched, products, statuses

    def _stem(self, kind: str) -> str:
        """Name one of this campaign's artifacts, without an extension."""
        return output_stem(self.manifest.name, self.manifest.date, kind)

    def _name(self, kind: str, extension: str) -> str:
        """Name one of this campaign's artifacts, extension included."""
        return output_name(self.manifest.name, self.manifest.date, kind, extension)

    def run(
        self,
        *,
        enrich: bool = True,
        export: bool = True,
        site: bool | None = None,
        video: bool | None = None,
        report: bool = True,
    ) -> RunResult:
        """Run the requested raw-to-artifacts workflow."""
        ds = self.process(self.ingest())
        products: dict[str, xr.Dataset] = {}
        statuses: list[dict[str, str]] = []
        if enrich and self.manifest.products:
            ds, products, statuses = self.enrich(ds)
        ds.attrs.update(
            campaign=self.manifest.name,
            manifest_sha256=self.manifest.digest,
            code_sha256=_code_hash(),
        )
        output = self.manifest.resolve_path(self.manifest.outputs.get("directory", "output"))
        output.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, Path] = {}
        if export:
            artifacts.update(
                export_dataset(
                    ds,
                    output,
                    self.manifest.outputs.get("formats", ["netcdf"]),
                    stem=self._stem("track"),
                )
            )
            for name, product in products.items():
                path = output / "products" / self._name(f"product-{name}", "nc")
                path.parent.mkdir(parents=True, exist_ok=True)
                product.to_netcdf(path, engine="h5netcdf", encoding=netcdf_encoding(product))
                artifacts[f"product:{name}"] = path
        make_site = self.manifest.outputs.get("site", False) if site is None else site
        if make_site:
            site_options: dict[str, Any] = self.manifest.outputs.get("site_options", {})
            # One file beside the other products is the default; a folder of
            # assets needing a server is the deliberate alternative.
            one_file = bool(self.manifest.outputs.get("single_html", True))
            destination = (
                output / site_filename(self.manifest.name, self.manifest.date)
                if one_file
                else output / self._stem("site")
            )
            artifacts["site"] = build_site(
                ds,
                destination,
                title=self.manifest.title,
                single_file=one_file,
                qc_config=self.manifest.qc,
                phase_config=self.manifest.phases,
                **site_options,
            )
        make_video = self.manifest.outputs.get("video", False) if video is None else video
        if make_video:
            video_config: dict[str, Any] = self.manifest.outputs.get("video_options", {})
            artifacts["video"] = render_video(
                ds, output / self._name("video", "mp4"), **video_config
            )
        summary: dict[str, Any] = {}
        if report:
            summary = summarise(
                ds,
                manifest=self.manifest,
                platform=load_platform(self.manifest.path.parent),
                artifacts=artifacts,
                products=statuses,
            )
            artifacts.update(write_report(summary, output, stem=self._stem("report")))
        logger.success("Pipeline complete for {}", self.manifest.name)
        return RunResult(ds, products, artifacts, statuses, summary)
