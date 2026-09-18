"""Safe import and local processing of browser-uploaded OceanPack logs."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date as calendar_date
from pathlib import Path
from typing import Any

from .errors import YachtCO2Error
from .manifest import CampaignManifest, default_template
from .pipeline import Pipeline, RunResult
from .project import read_yaml

DEFAULT_MAX_FILES = 100
DEFAULT_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
_DATE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?\Z")


def normalise_campaign_id(name: str, date: str) -> str:
    """Return the stable folder ID for a user-entered campaign and ISO date."""
    name = name.strip()
    date = date.strip()
    if not name:
        raise YachtCO2Error("A campaign name is required.")
    if not _DATE.fullmatch(date):
        raise YachtCO2Error("Campaign date must be YYYY-MM or YYYY-MM-DD.")
    if len(date) == 10:
        try:
            calendar_date.fromisoformat(date)
        except ValueError as exc:
            raise YachtCO2Error("Campaign date must be YYYY-MM or YYYY-MM-DD.") from exc
    slug = re.sub(r"[ -]", "_", name.lower())
    slug = re.sub(r"[^a-z0-9_]+", "_", slug).strip("_")
    if not slug:
        raise YachtCO2Error("Campaign name must contain a letter or number.")
    return f"{slug}-{date}"


@dataclass(frozen=True)
class UploadLimits:
    """Limits applied before any uploaded bytes reach a campaign folder."""

    max_files: int = DEFAULT_MAX_FILES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES


def upload_limits(settings: Mapping[str, Any] | None = None) -> UploadLimits:
    """Read configurable GUI limits, retaining safe defaults for malformed values."""
    settings = settings or {}
    configured = settings.get("raw_import", {})
    configured = configured if isinstance(configured, Mapping) else {}

    def integer(key: str, default: int) -> int:
        value = configured.get(key, os.environ.get(f"YACHT_CO2_RAW_IMPORT_{key.upper()}", default))
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    return UploadLimits(
        max_files=max(1, integer("max_files", DEFAULT_MAX_FILES)),
        max_total_bytes=max(1, integer("max_total_bytes", DEFAULT_MAX_TOTAL_BYTES)),
    )


@dataclass(frozen=True)
class RawLog:
    """One complete browser upload, kept separate from its destination path."""

    name: str
    content: bytes


def _safe_log_name(name: str) -> str:
    if not name or "\x00" in name or "/" in name or "\\" in name:
        raise YachtCO2Error(f"Unsafe upload filename: {name!r}")
    path = Path(name)
    if path.name != name or name in {".", ".."} or any(c in name for c in "\r\n"):
        raise YachtCO2Error(f"Unsafe upload filename: {name!r}")
    if path.suffix.lower() != ".log":
        raise YachtCO2Error(f"Only .log files can be imported: {name}")
    return name


def import_raw_logs(
    data_root: str | Path,
    name: str,
    date: str,
    files: Iterable[RawLog],
    *,
    limits: UploadLimits | None = None,
) -> Path:
    """Stage uploads then atomically create their new campaign directory.

    Existing folders and their source files are never changed. A validation or
    I/O failure removes only this call's private staging directory.
    """
    campaign_id = normalise_campaign_id(name, date)
    root = Path(data_root).expanduser().resolve()
    limits = limits or UploadLimits()
    selected = list(files)
    if not selected:
        raise YachtCO2Error("Select at least one .log file.")
    if len(selected) > limits.max_files:
        raise YachtCO2Error(f"At most {limits.max_files} log files can be imported at once.")
    names = [_safe_log_name(file.name) for file in selected]
    if len(set(names)) != len(names):
        raise YachtCO2Error("Each uploaded log must have a distinct filename.")
    total = sum(len(file.content) for file in selected)
    if total > limits.max_total_bytes:
        raise YachtCO2Error(
            f"Uploads total {total:,} bytes; the limit is {limits.max_total_bytes:,} bytes."
        )

    root.mkdir(parents=True, exist_ok=True)
    destination = root / campaign_id
    if destination.exists():
        raise YachtCO2Error(f"Campaign already exists: {campaign_id}")
    stage = Path(tempfile.mkdtemp(prefix=".yacht-co2-upload-", dir=root))
    claimed = False
    moved: list[Path] = []
    try:
        for file, filename in zip(selected, names, strict=True):
            (stage / filename).write_bytes(file.content)
        # mkdir is an exclusive ownership claim. Unlike replacing the staged
        # directory, it cannot overwrite an empty campaign created by another
        # request between our initial exists check and this point.
        try:
            destination.mkdir()
        except FileExistsError as exc:
            raise YachtCO2Error(f"Campaign already exists: {campaign_id}") from exc
        claimed = True
        for filename in names:
            target = destination / filename
            (stage / filename).replace(target)
            moved.append(target)
        stage.rmdir()
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        if claimed:
            # Remove only files made by this action. If something else wrote
            # into the newly claimed folder, leave that data alone instead of
            # recursively deleting a directory we no longer exclusively own.
            for target in moved:
                target.unlink(missing_ok=True)
            try:
                destination.rmdir()
            except OSError:
                pass
        raise
    return destination


def process_raw_logs_directly(folder: str | Path, name: str, date: str) -> RunResult:
    """Process local logs using the current defaults, without archiving them.

    This intentionally does not write a manifest or alter raw files. It is a
    direct, local result from the same defaults used for a normal manifest.
    """
    folder = Path(folder).resolve()
    campaign_id = normalise_campaign_id(name, date)
    template = read_yaml(default_template())
    inputs = dict(template.get("inputs", {}))
    inputs.pop("repository", None)
    inputs["logs"] = "./*.log"
    outputs = dict(template.get("outputs", {}))
    outputs["directory"] = "."
    manifest = CampaignManifest(
        path=folder / "manifest.yaml",
        campaign={"id": campaign_id, "name": name.strip(), "date": date.strip()},
        inputs=inputs,
        columns=dict(template.get("columns", {})),
        phases=dict(template.get("phases", {})),
        calibration=dict(template.get("calibration", {})),
        equilibrator=dict(template.get("equilibrator", {})),
        qc=dict(template.get("qc", {})),
        atmosphere=dict(template.get("atmosphere", {})),
        products=list(template.get("products", [])),
        flux=dict(template.get("flux", {})),
        outputs=outputs,
        raw={**template, "campaign": {"id": campaign_id, "name": name.strip(), "date": date.strip()}, "inputs": inputs, "outputs": outputs},
    )
    return Pipeline(manifest).run()
