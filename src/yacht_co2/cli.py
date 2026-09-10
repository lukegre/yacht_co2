"""Command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import xarray as xr

from .export import export_dataset
from .manifest import check_manifest, load_manifest
from .pipeline import Pipeline
from .project import PROJECT_CONFIG_ENV, config_paths, load_platform, load_project_config
from .report import summarise, write_report
from .site import build_site
from .validation import Finding, errors, validate_project_document
from .video import render_video

app = typer.Typer(help="Process and explore underway yacht CO2 observations.", no_args_is_help=True)


def _echo_findings(source: str, findings: list[Finding]) -> None:
    """Print one file's findings, worst first, or say that it is clean."""
    if not findings:
        typer.echo(f"{source}: ok")
        return
    for finding in sorted(findings, key=lambda item: item.severity != "error"):
        typer.echo(f"{source}: {finding}")


@app.command()
def validate(
    manifest: Optional[Path] = typer.Argument(  # noqa: UP045 - typer needs an explicit Optional
        None, exists=True, readable=True, help="Expedition manifest to check."
    ),
) -> None:
    """Validate the project configuration and, if given, an expedition manifest.

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
    pipeline.process(pipeline.ingest()).to_netcdf(output, engine="h5netcdf")
    typer.echo(output)


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
def site(input: Path, output: Path = Path("site"), single_file: bool = False) -> None:
    """Build a static interactive application."""
    typer.echo(build_site(xr.open_dataset(input).load(), output, single_file=single_file))


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
    for path in write_report(summary, output).values():
        typer.echo(path)


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
