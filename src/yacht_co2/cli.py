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
from .project import (
    PROJECT_CONFIG_ENV,
    config_paths,
    load_platform,
    load_project_config,
    read_yaml,
)
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


def _campaign_identity(
    config: Path, campaign: str | None, campaign_date: str | None
) -> tuple[str, str]:
    """Resolve the campaign name and date that name the upload and the site.

    A command-line value wins over the folder's configuration, which is where
    the campaign belongs: it is a fact about one race rather than the project.
    The upload has already validated the file, so it is only read here.
    """
    document = read_yaml(config) if config.is_file() else {}
    name = str(campaign or document.get("campaign") or "").strip()
    when = str(campaign_date or document.get("campaign_date") or "").strip()
    missing = [key for key, value in (("--campaign", name), ("--campaign-date", when)) if not value]
    if missing:
        raise typer.BadParameter(
            f"{config} does not name the campaign; pass {' and '.join(missing)}"
        )
    return name, when


def _campaign_manifest(folder: Path, config: Path) -> Path:
    """Return the campaign manifest, building it only if there is not one yet.

    A rerun resumes rather than starts again, so an existing manifest is kept:
    it is meant to be tuned by hand, and rebuilding it would discard that. It
    can still be stale, so a manifest pointing at a different record than the
    configuration does is reported without stopping the run.
    """
    manifest_path = folder / MANIFEST_NAME
    if not manifest_path.is_file():
        return build_manifest(config)

    logger.info("Reusing the campaign manifest {}", manifest_path)
    archived = str(read_yaml(config).get("doi") or "").strip()
    processing = str(read_yaml(manifest_path).get("inputs", {}).get("repository") or "").strip()
    if archived and processing and archived != processing:
        logger.warning(
            "{} reads {} but {} now names {}; delete the manifest to rebuild it",
            manifest_path.name,
            processing,
            config.name,
            archived,
        )
    return manifest_path


@app.command("pipeline")
def process_all(
    config: Optional[Path] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None,
        exists=True,
        dir_okay=False,
        readable=True,
        help=f"Campaign {ZENODO_CONFIG_NAME}; its folder is the one processed. "
        "Defaults to the current directory's.",
    ),
    campaign: Optional[str] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None, help="Campaign name; overrides the configuration."
    ),
    campaign_date: Optional[str] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None,
        "--campaign-date",
        metavar="YYYY[-MM[-DD]]",
        help="Campaign date; overrides the configuration.",
    ),
) -> None:
    """Upload and process a campaign folder.

    The folder is the one holding ``--config``, or the current directory. Its
    ``zenodo.yaml`` names the campaign, so the two campaign options are needed
    only to override that file or to write one for a folder that has none.
    """
    config_path = (
        config.resolve() if config is not None else Path.cwd().resolve() / ZENODO_CONFIG_NAME
    )
    folder = config_path.parent

    try:
        upload_raw_folder(
            folder,
            campaign=campaign,
            campaign_date=campaign_date,
            config=config,
            publish=True,
        )
    except RecordPublishedError as exc:
        # The archive already holds this folder, so there is nothing to upload
        # and every product below is still built from the published record.
        logger.info("{}; processing the published record", exc)
    except ZenodoError as exc:
        raise typer.BadParameter(str(exc)) from exc

    # The upload writes a configuration for a folder that had none, so the
    # campaign can now be read back from the file rather than the options.
    campaign, campaign_date = _campaign_identity(config_path, campaign, campaign_date)

    manifest_path = _campaign_manifest(folder, config_path)
    manifest = load_manifest(manifest_path)

    # Products are built from the archived record rather than the folder they
    # were uploaded from, so what is published is provably what was processed.
    outputs = {
        **manifest.outputs,
        "directory": str(folder),
        "formats": ["csv"],
        "site": False,
        "single_html": False,
        "video": False,
    }
    run_manifest = replace(manifest, outputs=outputs)
    try:
        result = Pipeline(run_manifest).run(enrich=False, site=False, video=False, report=False)
    except ZenodoError as exc:
        # A just-submitted record is not public until a curator accepts it, so
        # its files cannot be read back yet. The local logs are the ones that
        # were uploaded, so they stand in until the record is available.
        logger.warning("Could not read the archived record ({}); using the local logs", exc)
        local_inputs = dict(manifest.inputs)
        local_inputs.pop("repository", None)
        result = Pipeline(replace(run_manifest, inputs=local_inputs)).run(
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
