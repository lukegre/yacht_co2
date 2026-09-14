"""Command-line interface."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Optional

import typer
import xarray as xr
from loguru import logger

from .errors import RecordPublishedError, ZenodoError
from .export import export_dataset
from .manifest import MANIFEST_NAME, build_manifest, check_manifest, load_manifest
from .pipeline import Pipeline
from .project import PROJECT_CONFIG_ENV, config_paths, load_platform, load_project_config
from .report import summarise, write_report
from .site import build_site, site_filename
from .validation import Finding, errors, validate_project_document
from .video import render_video
from .zenodo import CONFIG_NAME as ZENODO_CONFIG_NAME
from .zenodo import upload_raw_folder

app = typer.Typer(help="Process and explore underway yacht CO2 observations.", no_args_is_help=True)


def _echo_findings(source: str, findings: list[Finding]) -> None:
    """Print one file's findings, worst first, or say that it is clean."""
    if not findings:
        typer.echo(f"{source}: ok")
        return
    for finding in sorted(findings, key=lambda item: item.severity != "error"):
        typer.echo(f"{source}: {finding}")


@app.command("build-manifest")
def build_manifest_command(
    zenodo: Path = typer.Argument(..., exists=True, readable=True, help="Input zenodo.yaml."),
    output: Optional[Path] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None, help="Destination; defaults to manifest.yaml beside zenodo.yaml."
    ),
    defaults: Optional[Path] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None, exists=True, readable=True, help="Alternative manifest defaults YAML."
    ),
) -> None:
    """Build a processing manifest from Zenodo campaign metadata."""
    typer.echo(build_manifest(zenodo, output, defaults=defaults))


@app.command("pipeline")
def process_all(
    campaign: str = typer.Option(..., help="Campaign name used for the upload and site."),
    campaign_date: str = typer.Option(
        ...,
        "--campaign-date",
        metavar="YYYY[-MM[-DD]]",
        help="Campaign date used for the upload and site.",
    ),
) -> None:
    """Upload and process the campaign in the current directory."""
    folder = Path.cwd().resolve()
    manifest_path = folder / MANIFEST_NAME
    if manifest_path.exists():
        raise typer.BadParameter(
            f"manifest already exists: {manifest_path}; remove it only if it is safe to regenerate"
        )

    try:
        upload_raw_folder(
            folder,
            campaign=campaign,
            campaign_date=campaign_date,
            publish=True,
        )
    except RecordPublishedError as exc:
        # The archive already holds this folder, so there is nothing to upload
        # and every local product below can still be built against its DOI.
        logger.info("{}; processing the local logs against the published record", exc)
    except ZenodoError as exc:
        raise typer.BadParameter(str(exc)) from exc

    manifest_path = build_manifest(folder / ZENODO_CONFIG_NAME)
    manifest = load_manifest(manifest_path)

    # A just-submitted record may still be awaiting community review and its
    # reserved DOI may therefore not be public yet. Process the same local logs
    # that were uploaded, while retaining the DOI in the persisted manifest.
    local_inputs = dict(manifest.inputs)
    local_inputs.pop("repository", None)
    local_outputs = {
        **manifest.outputs,
        "directory": str(folder),
        "formats": ["csv"],
        "site": False,
        "single_html": False,
        "video": False,
    }
    local_manifest = replace(manifest, inputs=local_inputs, outputs=local_outputs)
    result = Pipeline(local_manifest).run(
        enrich=False,
        site=False,
        video=False,
        report=False,
    )

    site_path = folder / site_filename(campaign, campaign_date)
    result.artifacts["site"] = site_path
    result.summary = summarise(
        result.dataset,
        manifest=manifest,
        platform=load_platform(folder),
        artifacts=result.artifacts,
        products=result.product_status,
    )
    result.artifacts.update(write_report(result.summary, folder))
    build_site(
        result.dataset,
        site_path,
        title=f"{campaign} ({campaign_date})",
        single_file=True,
        report=result.summary,
        qc_config=manifest.qc,
    )

    for kind, path in result.artifacts.items():
        typer.echo(f"{kind}: {path}")


@app.command()
def validate(
    manifest: Optional[Path] = typer.Argument(  # noqa: UP045 - typer needs an explicit Optional
        None, exists=True, readable=True, help="Campaign manifest to check."
    ),
) -> None:
    """Validate the project configuration and, if given, a campaign manifest.

    Errors are problems that stop a run; warnings are keys nothing reads or
    values that look mistaken but still work. Exits non-zero only for errors.
    """
    start = manifest.parent if manifest else Path.cwd()
    paths = config_paths(start)
    project_findings: list[Finding] = []
    if not paths:
        typer.echo(f"no project configuration found (set {PROJECT_CONFIG_ENV} or add project.yaml)")
    else:
        for path in paths:
            typer.echo(f"project configuration: {path}")
        project_findings = validate_project_document(
            load_project_config(start), source="project configuration"
        )
        _echo_findings("project configuration", project_findings)

    manifest_findings: list[Finding] = []
    if manifest is not None:
        _, manifest_findings = check_manifest(manifest)
        _echo_findings(str(manifest), manifest_findings)
        if not errors(manifest_findings):
            loaded = load_manifest(manifest)
            typer.echo(f"valid: {loaded.name} ({loaded.digest})")
    if errors(project_findings + manifest_findings):
        raise typer.Exit(code=1)


@app.command()
def ingest(manifest: Path, output: Path = Path("ingested.nc")) -> None:
    """Ingest raw logs only."""
    Pipeline(manifest).ingest().to_netcdf(output, engine="h5netcdf")
    typer.echo(output)


@app.command()
def process(manifest: Path, output: Path = Path("processed.nc")) -> None:
    """Ingest and perform local scientific processing."""
    pipeline = Pipeline(manifest)
    destination = output.expanduser().resolve()
    pipeline.process(pipeline.ingest()).to_netcdf(destination, engine="h5netcdf")
    logger.success("Saved processed dataset to {}", destination)
    typer.echo(destination)


@app.command()
def enrich(manifest: Path, input: Path, output: Path = Path("enriched.nc")) -> None:
    """Fetch and collocate products onto an existing track."""
    ds, _, _ = Pipeline(manifest).enrich(xr.open_dataset(input).load())
    ds.to_netcdf(output, engine="h5netcdf")
    typer.echo(output)


@app.command("export")
def export_command(input: Path, output: Path, formats: str = "netcdf,csv") -> None:
    """Export a canonical dataset."""
    paths = export_dataset(xr.open_dataset(input).load(), output, formats.split(","))
    typer.echo("\n".join(str(path) for path in paths.values()))


@app.command()
def site(
    input: Path,
    output: Path = Path("site"),
    single_file: bool = False,
    report: Optional[Path] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None, help="report.json to embed as a campaign info panel."
    ),
) -> None:
    """Build a static interactive application.

    If --report is not given, looks for a report.json next to the input
    dataset or next to the output path and embeds it automatically.
    """
    report_path = report
    if report_path is None:
        output_dir = output if output.suffix == "" else output.parent
        for candidate in (input.parent / "report.json", output_dir / "report.json"):
            if candidate.exists():
                report_path = candidate
                break
    report_data = json.loads(report_path.read_text()) if report_path else None
    typer.echo(
        build_site(
            xr.open_dataset(input).load(),
            output,
            single_file=single_file,
            report=report_data,
        )
    )


@app.command()
def video(input: Path, output: Path = Path("track.mp4"), variable: str = "pco2_seawater") -> None:
    """Render a synchronized H.264 video."""
    typer.echo(render_video(xr.open_dataset(input).load(), output, variable=variable))


@app.command("report")
def report_command(
    input: Path,
    output: Path = Path("."),
    manifest: Optional[Path] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None, help="Manifest supplying platform identity."
    ),
) -> None:
    """Write report.json and REPORT.md for an existing dataset."""
    loaded = load_manifest(manifest) if manifest else None
    summary = summarise(
        xr.open_dataset(input).load(),
        manifest=loaded,
        platform=load_platform(loaded.path.parent if loaded else input),
    )
    labels = {"report_json": "JSON report", "report_markdown": "Markdown report"}
    for kind, path in write_report(summary, output).items():
        typer.echo(f"{labels[kind]}: {path}")


@app.command()
def run(
    manifest: Path,
    no_enrich: bool = typer.Option(False, help="Skip all remote products."),
    no_export: bool = typer.Option(False, help="Skip dataset exports."),
) -> None:
    """Run the complete manifest-driven pipeline."""
    result = Pipeline(manifest).run(enrich=not no_enrich, export=not no_export)
    for kind, path in result.artifacts.items():
        typer.echo(f"{kind}: {path}")


if __name__ == "__main__":
    app()
