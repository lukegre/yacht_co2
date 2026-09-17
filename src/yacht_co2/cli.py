"""Command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import xarray as xr

from .errors import YachtCO2Error
from .export import netcdf_encoding
from .manifest import MANIFEST_NAME, CampaignManifest, build_manifest, check_manifest, load_manifest
from .naming import output_stem
from .pipeline import Pipeline
from .project import PROJECT_CONFIG_ENV, config_paths, load_project_config
from .site import build_site, site_filename
from .validation import Finding, errors, validate_project_document
from .workflow import processed_dataset, run_campaign

APP_HELP = """Process and explore underway yacht CO2 observations.

A campaign is one command, [bold]yacht-co2 run manifest.yaml[/bold], which:

\b
  1. archives the campaign folder's raw logs on Zenodo (skipped when the
     checksums show this folder was already uploaded);
  2. reads the logs back from the archived record, so what is published is
     provably what was processed;
  3. ingests and processes them into a quality-controlled track;
  4. exports the dataset beside the manifest;
  5. writes the JSON run report;
  6. builds the single-file interactive site.

[bold]build-manifest[/bold] writes the manifest that run takes; [bold]enrich[/bold]
and [bold]site[/bold] redo one step of the procedure on its own. [bold]gui[/bold]
opens the same procedure in a browser, for a machine with no Python on it.
"""

app = typer.Typer(help=APP_HELP, no_args_is_help=True, rich_markup_mode="rich")


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


def _site_destination(
    manifest: CampaignManifest,
    directory: Path,
    output: Path | None,
    single_file: bool | None,
) -> tuple[Path, bool]:
    """Return where to build the site and whether it is one file.

    One self-contained file named after the campaign, written straight into
    the output directory, is the default; ``outputs.single_html: false`` asks
    for the hosted bundle instead, which is the only form that needs a folder.
    """
    if output is not None:
        # A named destination says what it is: --output page.html is one file.
        return output, single_file if single_file is not None else output.suffix == ".html"
    if single_file is None:
        single_file = bool(manifest.outputs.get("single_html", True))
    if single_file:
        return directory / site_filename(manifest.name, manifest.date), True
    return directory / output_stem(manifest.name, manifest.date, "site"), False


@app.command("run")
def run(
    manifest: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help=f"Campaign {MANIFEST_NAME}; its folder is the one processed.",
    ),
) -> None:
    """Archive a campaign on Zenodo and build every product from the record.

    \b
    The manifest's folder is the campaign, and the run:
      1. uploads its raw logs to Zenodo, unless the checksums recorded by an
         earlier run show that this folder is already archived;
      2. reads the logs back from the archived record, so what is published is
         provably what was processed (the local logs stand in while a
         just-submitted record is still awaiting review);
      3. ingests and processes them into a quality-controlled track;
      4. exports the dataset beside the manifest;
      5. writes the JSON run report;
      6. builds the single-file interactive site.

    Nothing is redone: an existing upload or product is kept, so a rerun
    resumes where the last one stopped. Write the manifest first with
    [bold]yacht-co2 build-manifest zenodo.yaml[/bold].
    """
    try:
        result = run_campaign(manifest)
    except YachtCO2Error as exc:
        raise typer.BadParameter(str(exc)) from exc
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
def enrich(manifest: Path, input: Path, output: Path = Path("enriched.nc")) -> None:
    """Fetch and collocate products onto an existing track."""
    ds, _, _ = Pipeline(manifest).enrich(xr.open_dataset(input).load())
    ds.to_netcdf(output, engine="h5netcdf", encoding=netcdf_encoding(ds))
    typer.echo(output)


@app.command()
def site(
    manifest: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True, help=f"Campaign {MANIFEST_NAME}."
    ),
    output: Optional[Path] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None, help="Build one site here instead of the destinations outputs names."
    ),
    single_file: Optional[bool] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None,
        "--single-file/--no-single-file",
        help="Override outputs.single_html for this build.",
    ),
) -> None:
    """Build a static interactive application for a campaign.

    Every argument comes from the manifest: ``campaign`` titles and names the
    page, ``qc`` documents the flags, and ``outputs`` says where it goes, which
    of the hosted bundle and the single file to build, and what to pass through
    to the builder. The processed track NetCDF is reused when the output
    directory holds one; otherwise the campaign is processed first.
    """
    campaign = load_manifest(manifest)
    dataset, report, directory = processed_dataset(campaign)
    destination, one_file = _site_destination(campaign, directory, output, single_file)
    typer.echo(
        build_site(
            dataset,
            destination,
            title=campaign.title,
            single_file=one_file,
            report=report,
            qc_config=campaign.qc,
            phase_config=campaign.phases,
            **campaign.outputs.get("site_options", {}),
        )
    )


@app.command()
def gui(
    data_root: Optional[Path] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None,
        exists=True,
        file_okay=False,
        help="Folder holding the campaign folders; remembered between launches.",
    ),
    host: str = typer.Option("127.0.0.1", help="Address to serve on."),
    port: int = typer.Option(8080, help="Port to serve on."),
    root_path: Optional[str] = typer.Option(  # noqa: UP045 - typer needs an explicit Optional
        None,
        help="Reverse-proxy URL prefix; defaults to RENKU_BASE_URL_PATH when set.",
    ),
    show: bool = typer.Option(True, help="Open a browser window on start."),
    native: bool = typer.Option(
        False,
        help="Draw the pages in a window of their own, as the packaged application does.",
    ),
) -> None:
    """Open the whole procedure in a browser, for someone who does not use a terminal.

    The same five steps as the commands above -- archive, build a manifest,
    edit it, process, publish -- driven by forms rather than by flags, with the
    shared defaults kept in your own configuration directory so they outlive
    any one campaign. The server listens on this machine only unless ``--host``
    is set explicitly (for example, to ``0.0.0.0`` inside a container).
    """
    try:
        from .gui import launch
    except ImportError as exc:  # pragma: no cover - depends on how it was installed
        raise typer.BadParameter(
            f"the graphical interface needs its extra dependencies ({exc}); "
            "install them with: uv sync --extra gui"
        ) from exc
    if native:
        from .desktop import can_open_a_window

        if not can_open_a_window():
            raise typer.BadParameter(
                "a window needs pywebview, and on Linux a display as well; "
                "install it with: uv sync --extra desktop"
            )
        # A window finds its own port, the same as the packaged application.
        launch(
            data_root=data_root,
            host=host,
            port=None,
            root_path=root_path,
            show=False,
            native=True,
        )
        return
    launch(data_root=data_root, host=host, port=port, root_path=root_path, show=show)


if __name__ == "__main__":
    app()
