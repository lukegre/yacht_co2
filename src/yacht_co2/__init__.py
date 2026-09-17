"""Public API for yacht-co2."""

from .collocate import collocate_track, resolve_air_co2
from .export import export_dataset
from .ingest import read_campaign, read_expedition, read_log_file
from .manifest import CampaignManifest, ExpeditionManifest, build_manifest
from .pipeline import Pipeline, RunResult
from .project import load_platform, load_project_config
from .providers import fetch_products
from .qc import apply_qc
from .report import summarise, write_report
from .science import calibrate_co2, derive_fco2, derive_flux, derive_pco2
from .site import build_site
from .video import render_video
from .zenodo import (
    ZenodoClient,
    generate_zenodo_config,
    load_zenodo_config,
    parse_creators,
    upload_raw_folder,
)

__all__ = [
    "Pipeline",
    "RunResult",
    "CampaignManifest",
    "ExpeditionManifest",
    "apply_qc",
    "build_site",
    "build_manifest",
    "calibrate_co2",
    "collocate_track",
    "derive_fco2",
    "derive_flux",
    "derive_pco2",
    "export_dataset",
    "fetch_products",
    "load_platform",
    "load_project_config",
    "read_expedition",
    "read_campaign",
    "read_log_file",
    "render_video",
    "summarise",
    "write_report",
    "resolve_air_co2",
    "ZenodoClient",
    "generate_zenodo_config",
    "load_zenodo_config",
    "parse_creators",
    "upload_raw_folder",
]
