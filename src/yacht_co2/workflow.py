"""One campaign, end to end, and how far along it already is.

:mod:`yacht_co2.cli` and :mod:`yacht_co2.gui` drive the same procedure, so it
lives here rather than in either of them: a campaign archived from the terminal
and one archived from the browser must leave the folder in the same state, and
a rerun from either must resume where the other stopped.

:func:`campaign_status` answers the question an interface asks before it offers
a button -- which steps has this folder already been through -- by reading the
folder rather than any record kept about it, so a folder that arrived on a USB
stick is as legible as one this machine produced.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import xarray as xr
from loguru import logger

from .errors import ManifestError, RecordPublishedError, ZenodoError
from .manifest import MANIFEST_NAME, CampaignManifest, load_manifest
from .naming import output_name, output_stem
from .pipeline import Pipeline, RunResult
from .project import load_platform, read_yaml
from .report import summarise, write_report
from .site import build_site, site_filename
from .zenodo import CONFIG_NAME as ZENODO_CONFIG_NAME
from .zenodo import upload_raw_folder

PIPELINE_STATE_NAME = ".yacht-co2-pipeline.json"
UPLOAD_STATE_NAME = ".zenodo-upload.json"


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


def read_pipeline_state(folder: Path) -> dict[str, Any]:
    """Read the checkpoint a previous run left in ``folder``."""
    path = folder / PIPELINE_STATE_NAME
    if not path.is_file():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring invalid pipeline checkpoint {}", path)
        return {}
    return state if isinstance(state, dict) else {}


def write_upload_checkpoint(
    folder: Path, config: Path, upload: dict[str, Any] | None = None
) -> None:
    """Record the checksums that say this folder is the one already archived."""
    state = read_pipeline_state(folder)
    previous = state.get("zenodo_upload")
    previous = previous if isinstance(previous, dict) else None
    files = _checkpoint_files(folder, previous)
    state["version"] = 1
    state["zenodo_upload"] = {
        "record_id": str(
            (upload or {}).get("record_id") or (previous or {}).get("record_id") or ""
        ),
        "config_sha256": _sha256(config),
        "files": {
            path.name: {"sha256": _sha256(path), "size": path.stat().st_size} for path in files
        },
    }
    destination = folder / PIPELINE_STATE_NAME
    temporary = folder / f"{PIPELINE_STATE_NAME}.tmp"
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)


def read_upload_state(folder: Path) -> dict[str, Any]:
    """Read what the last Zenodo upload left in ``folder``.

    The state file carries the record's ``status`` -- ``draft``,
    ``pending_review`` or ``published`` -- which is the only local record of
    whether a curator has accepted the archive yet. An unreadable file is
    reported as no state at all, since it describes an upload nobody can
    resume anyway.
    """
    path = folder / UPLOAD_STATE_NAME
    if not path.is_file():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring invalid Zenodo upload state {}", path)
        return {}
    return state if isinstance(state, dict) else {}


def _legacy_upload_was_submitted(folder: Path, config: Path) -> bool:
    """Recognise upload state written before pipeline checksums were introduced."""
    upload_path = folder / UPLOAD_STATE_NAME
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


def upload_checkpoint_matches(folder: Path, config: Path) -> bool:
    """Say whether the archived record still describes this folder exactly."""
    state = read_pipeline_state(folder)
    checkpoint = state.get("zenodo_upload")
    if not isinstance(checkpoint, dict):
        if not _legacy_upload_was_submitted(folder, config):
            return False
        write_upload_checkpoint(folder, config)
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


def campaign_config(manifest: CampaignManifest) -> Path:
    """Return the Zenodo configuration beside the manifest, which names the archive."""
    config = manifest.path.parent / ZENODO_CONFIG_NAME
    if not config.is_file():
        raise ManifestError(f"{manifest.path.parent} holds no {ZENODO_CONFIG_NAME}")
    return config


def warn_when_manifest_is_stale(manifest: CampaignManifest, config: Path) -> None:
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


def run_campaign(manifest: str | Path) -> RunResult:
    """Optionally archive a campaign, then build every product from its logs.

    A manifest with ``inputs.repository`` follows the archived workflow. A
    manifest without it deliberately skips upload and reads its local logs.
    Either route processes the data, writes the report and builds the site.
    """
    manifest_path = Path(manifest).resolve()
    campaign_manifest = load_manifest(manifest_path)
    folder = manifest_path.parent
    config_path = campaign_config(campaign_manifest)
    warn_when_manifest_is_stale(campaign_manifest, config_path)

    campaign = campaign_manifest.name
    campaign_date = campaign_manifest.date
    if not campaign_date:
        raise ManifestError(f"{manifest_path} does not give the campaign date")

    repository = str(campaign_manifest.inputs.get("repository") or "").strip()
    if not repository:
        logger.info("Manifest uses local logs; skipping the Zenodo archive step")
    elif upload_checkpoint_matches(folder, config_path):
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
        write_upload_checkpoint(folder, config_path, upload)

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
    return result


def processed_dataset(
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


@dataclass(frozen=True)
class CampaignStatus:
    """How far one data folder has been taken through the procedure.

    Each field is read from the folder itself, so the answer is the same
    whoever produced it and whichever interface is asking.
    """

    folder: Path
    logs: list[Path] = field(default_factory=list)
    zenodo_config: Path | None = None
    manifest: Path | None = None
    doi: str = ""
    submitted: str = ""
    campaign: str = ""
    campaign_date: str = ""
    track: Path | None = None
    report: Path | None = None
    site: Path | None = None
    manifest_error: str = ""
    #: ``draft``, ``pending_review`` or ``published``, as the last upload left it.
    upload_status: str = ""
    #: True when the persisted manifest deliberately reads local logs.
    archive_skipped: bool = False

    @property
    def has_logs(self) -> bool:
        return bool(self.logs)

    @property
    def is_uploaded(self) -> bool:
        """True once a DOI has been reserved for this folder."""
        return bool(self.doi)

    @property
    def archive_complete(self) -> bool:
        """True when archiving succeeded or the manifest explicitly skips it."""
        return self.is_uploaded or self.archive_skipped

    @property
    def has_manifest(self) -> bool:
        return self.manifest is not None

    @property
    def is_processed(self) -> bool:
        return self.track is not None

    @property
    def is_published(self) -> bool:
        """True once the draft has been handed to its community for review."""
        return bool(self.submitted)

    @property
    def review_is_pending(self) -> bool:
        """True while a curator has yet to accept the archive.

        A record's files are frozen for as long as its review is open, so
        nothing more can be added to it until the community decides.
        """
        return self.upload_status == "pending_review"

    @property
    def title(self) -> str:
        """Name the campaign the way a reader should see it."""
        if not self.campaign:
            return self.folder.name
        return f"{self.campaign} ({self.campaign_date})" if self.campaign_date else self.campaign


def _artifact(directory: Path, campaign: str, date: str, kind: str, extension: str) -> Path | None:
    """Return one named artifact of a campaign, if it has been written."""
    if not campaign:
        return None
    try:
        path = directory / output_name(campaign, date, kind, extension)
    except ValueError:
        return None
    return path if path.is_file() else None


def campaign_status(folder: str | Path) -> CampaignStatus:
    """Read how far ``folder`` has been taken through the procedure.

    Nothing here raises: a half-written folder is exactly what an interface
    needs to describe, and a manifest that cannot be loaded is reported as the
    reason its later steps are unavailable rather than as a failure.
    """
    folder = Path(folder).resolve()
    zenodo_path = folder / ZENODO_CONFIG_NAME
    manifest_path = folder / MANIFEST_NAME

    zenodo_document: dict[str, Any] = {}
    if zenodo_path.is_file():
        try:
            zenodo_document = read_yaml(zenodo_path)
        except ManifestError as exc:
            logger.warning("Could not read {}: {}", zenodo_path, exc)

    campaign = str(zenodo_document.get("campaign") or zenodo_document.get("title") or "").strip()
    campaign_date = str(zenodo_document.get("campaign_date") or "").strip()
    pattern = "./*.log"
    manifest_error = ""
    directory = folder
    archive_skipped = False

    if manifest_path.is_file():
        try:
            loaded = load_manifest(manifest_path)
        except ManifestError as exc:
            manifest_error = str(exc)
        else:
            campaign = loaded.name
            campaign_date = loaded.date
            pattern = str(loaded.inputs.get("logs") or pattern)
            directory = loaded.resolve_path(loaded.outputs.get("directory", "."))
            archive_skipped = not bool(str(loaded.inputs.get("repository") or "").strip())

    logs = sorted(
        path
        for path in folder.glob(pattern.removeprefix("./"))
        if path.is_file() and path.parent == folder and not path.is_symlink()
    )
    return CampaignStatus(
        folder=folder,
        logs=logs,
        zenodo_config=zenodo_path if zenodo_path.is_file() else None,
        manifest=manifest_path if manifest_path.is_file() else None,
        doi=str(zenodo_document.get("doi") or "").strip(),
        submitted=str(zenodo_document.get("submitted") or "").strip(),
        campaign=campaign,
        campaign_date=campaign_date,
        track=_artifact(directory, campaign, campaign_date, "track", "nc"),
        report=_artifact(directory, campaign, campaign_date, "report", "json"),
        site=_artifact(directory, campaign, campaign_date, "site", "html"),
        manifest_error=manifest_error,
        upload_status=str(read_upload_state(folder).get("status") or ""),
        archive_skipped=archive_skipped,
    )


def find_campaigns(root: str | Path) -> list[CampaignStatus]:
    """Describe every immediate sub-folder of ``root`` that holds a campaign.

    A folder counts when it holds raw logs or has been through any step, which
    keeps the listing to the folders someone would actually pick while still
    showing one whose logs have been archived and removed.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        return []
    found: list[CampaignStatus] = []
    for candidate in sorted(root.iterdir()):
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue
        status = campaign_status(candidate)
        if status.has_logs or status.zenodo_config or status.manifest:
            found.append(status)
    return found
