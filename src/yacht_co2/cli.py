"""Command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
import xarray as xr

from .export import export_dataset
from .manifest import load_manifest
from .pipeline import Pipeline
from .site import build_site
from .video import render_video

app = typer.Typer(help="Process and explore underway yacht CO2 observations.", no_args_is_help=True)


@app.command()
def validate(manifest: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Validate an expedition manifest."""
    loaded = load_manifest(manifest)
    typer.echo(f"valid: {loaded.name} ({loaded.digest})")


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
