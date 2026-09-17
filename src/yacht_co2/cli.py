"""Command-line interface."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

import typer
import xarray as xr
from loguru import logger

from .errors import RecordPublishedError, ZenodoError
from .export import netcdf_encoding
from .manifest import (
    MANIFEST_NAME,
    CampaignManifest,
    build_manifest,
    check_manifest,
    load_manifest,
)
from .naming import output_name, output_stem
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
from .zenodo import CONFIG_NAME as ZENODO_CONFIG_NAME
from .zenodo import upload_raw_folder

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
and [bold]site[/bold] redo one step of the procedure on its own.
"""

app = typer.Typer(help=APP_HELP, no_args_is_help=True, rich_markup_mode="rich")
PIPELINE_STATE_NAME = ".yacht-co2-pipeline.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_raw_files(folder: Path) -> set[Path]:
    """Return top-level raw inputs named by an existing campaign manifest."""
    manifest_path = folder / MANIFEST_NAME
    if not manifest_path.is_file():
        return set()
    manifest = read_yaml(manifest_path)
    pattern = str(manifest.get("inputs", {}).get("logs") or "./*.log")
    return {
        path
        for path in folder.glob(pattern.removeprefix("./"))
        if path.is_file() and path.parent == folder and not path.is_symlink()
    }


def _checkpoint_files(folder: Path, previous: dict[str, Any] | None = None) -> list[Path]:
    """Select raw files without mistaking products from a prior run for inputs."""
    paths = _manifest_raw_files(folder)
    if previous:
        for name in previous.get("files", {}):
            path = folder / name
            if path.is_file() and path.parent == folder and not path.is_symlink():
                paths.add(path)
    if paths:
        return sorted(paths, key=lambda path: path.name)
    return sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and not path.name.startswith(".")
            and path.name != ZENODO_CONFIG_NAME
        ),
        key=lambda path: path.name,
    )


def _read_pipeline_state(folder: Path) -> dict[str, Any]:
    path = folder / PIPELINE_STATE_NAME
    if not path.is_file():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring invalid pipeline checkpoint {}", path)
        return {}
    return state if isinstance(state, dict) else {}


def _write_upload_checkpoint(
    folder: Path, config: Path, upload: dict[str, Any] | None = None
) -> None:
    state = _read_pipeline_state(folder)
    previous = state.get("zenodo_upload")
    previous = previous if isinstance(previous, dict) else None
    files = _checkpoint_files(folder, previous)
    state["version"] = 1
    state["zenodo_upload"] = {
        "record_id": str((upload or {}).get("record_id") or (previous or {}).get("record_id") or ""),
        "config_sha256": _sha256(config),
        "files": {
            path.name: {"sha256": _sha256(path), "size": path.stat().st_size} for path in files
        },
    }
    destination = folder / PIPELINE_STATE_NAME
    temporary = folder / f"{PIPELINE_STATE_NAME}.tmp"
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)


def _legacy_upload_was_submitted(folder: Path, config: Path) -> bool:
    """Recognise upload state written before pipeline checksums were introduced."""
    upload_path = folder / ".zenodo-upload.json"
    if not upload_path.is_file():
        return False
    try:
        upload = json.loads(upload_path.read_text(encoding="utf-8"))
        configured = read_yaml(config)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return bool(
        isinstance(upload, dict)
        and upload.get("record_id")
        and upload.get("review_url")
        and configured.get("doi")
        and configured.get("submitted")
    )


def _upload_checkpoint_matches(folder: Path, config: Path) -> bool:
    state = _read_pipeline_state(folder)
    checkpoint = state.get("zenodo_upload")
    if not isinstance(checkpoint, dict):
        if not _legacy_upload_was_submitted(folder, config):
            return False
        _write_upload_checkpoint(folder, config)
        logger.info("Recorded checksum checkpoint for the previously submitted Zenodo upload")
        return True

    files = checkpoint.get("files")
    if not isinstance(files, dict) or checkpoint.get("config_sha256") != _sha256(config):
        return False
    for name, expected in files.items():
        path = folder / name
        if (
            not isinstance(expected, dict)
            or not path.is_file()
            or path.is_symlink()
            or path.parent != folder
            or expected.get("size") != path.stat().st_size
            or expected.get("sha256") != _sha256(path)
        ):
            return False
    if {path.name for path in _manifest_raw_files(folder)} - set(files):
        return False
    return True


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


def _campaign_config(manifest: CampaignManifest) -> Path:
    """Return the Zenodo configuration beside the manifest, which names the archive."""
    config = manifest.path.parent / ZENODO_CONFIG_NAME
    if not config.is_file():
        raise typer.BadParameter(f"{manifest.path.parent} holds no {ZENODO_CONFIG_NAME}")
    return config


def _warn_when_manifest_is_stale(manifest: CampaignManifest, config: Path) -> None:
    """Report a manifest pointing at a different record than the configuration does.

    The manifest is meant to be tuned by hand, so it is never rebuilt behind
    the operator's back: a mismatch is named and the run goes on.
    """
    archived = str(read_yaml(config).get("doi") or "").strip()
    processing = str(manifest.inputs.get("repository") or "").strip()
    if archived and processing and archived != processing:
        logger.warning(
            "{} reads {} but {} now names {}; rebuild the manifest to process the new record",
            manifest.path.name,
            processing,
            config.name,
            archived,
        )


def _processed_dataset(
    manifest: CampaignManifest,
) -> tuple[xr.Dataset, dict[str, Any] | None, Path]:
    """Return the campaign's processed dataset, its report, and their directory.

    Processing a campaign is slow and its result is an artifact in its own
    right, so an existing track NetCDF is reused rather than rebuilt. When
    there is none the campaign is processed and exported as NetCDF -- adding
    that format if the manifest omits it -- so that the next build can reuse it.
    """
    directory = manifest.resolve_path(manifest.outputs.get("directory", "output"))
    dataset_path = directory / output_name(manifest.name, manifest.date, "track", "nc")
    if dataset_path.is_file():
        logger.info("Reusing the processed dataset {}", dataset_path)
        report_path = directory / output_name(manifest.name, manifest.date, "report", "json")
        report = json.loads(report_path.read_text()) if report_path.is_file() else None
        return xr.open_dataset(dataset_path).load(), report, directory

    logger.info("No processed dataset at {}; processing the campaign first", dataset_path)
    formats = [str(fmt) for fmt in manifest.outputs.get("formats", ["netcdf"])]
    if not any(fmt.lower() in {"netcdf", "nc", ".nc"} for fmt in formats):
        formats.append("netcdf")
    outputs = {**manifest.outputs, "formats": formats}
    result = Pipeline(replace(manifest, outputs=outputs)).run(site=False, video=False)
    return result.dataset, result.summary or None, directory


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
    manifest_path = manifest.resolve()
    campaign_manifest = load_manifest(manifest_path)
    folder = manifest_path.parent
    config_path = _campaign_config(campaign_manifest)
    _warn_when_manifest_is_stale(campaign_manifest, config_path)

    campaign = campaign_manifest.name
    campaign_date = campaign_manifest.date
    if not campaign_date:
        raise typer.BadParameter(f"{manifest_path} does not give the campaign date")

    if _upload_checkpoint_matches(folder, config_path):
        logger.info("Zenodo upload checksums match; continuing with the processing pipeline")
    else:
        upload: dict[str, Any] | None = None
        try:
            upload = upload_raw_folder(
                folder,
                campaign=campaign,
                campaign_date=campaign_date,
                config=config_path,
                publish=True,
            )
        except RecordPublishedError as exc:
            # The archive already holds this folder, so there is nothing to upload
            # and every product below is still built from the published record.
            logger.info("{}; processing the published record", exc)
        except ZenodoError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _write_upload_checkpoint(folder, config_path, upload)

    # Products are built from the archived record rather than the folder they
    # were uploaded from, so what is published is provably what was processed.
    outputs = {
        **campaign_manifest.outputs,
        "directory": str(folder),
        "site": False,
        "single_html": False,
        "video": False,
    }
    run_manifest = replace(campaign_manifest, outputs=outputs)
    try:
        result = Pipeline(run_manifest).run(enrich=False, site=False, video=False, report=False)
    except ZenodoError as exc:
        # A just-submitted record is not public until a curator accepts it, so
        # its files cannot be read back yet. The local logs are the ones that
        # were uploaded, so they stand in until the record is available.
        logger.warning("Could not read the archived record ({}); using the local logs", exc)
        local_inputs = dict(campaign_manifest.inputs)
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
        manifest=campaign_manifest,
        platform=load_platform(folder),
        artifacts=result.artifacts,
        products=result.product_status,
    )
    result.artifacts.update(
        write_report(result.summary, folder, stem=output_stem(campaign, campaign_date, "report"))
    )
    build_site(
        result.dataset,
        site_path,
        title=campaign_manifest.title,
        single_file=True,
        report=result.summary,
        qc_config=campaign_manifest.qc,
        phase_config=campaign_manifest.phases,
        **campaign_manifest.outputs.get("site_options", {}),
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
    dataset, report, directory = _processed_dataset(campaign)
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


if __name__ == "__main__":
    app()
