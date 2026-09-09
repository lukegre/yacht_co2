"""Up-front validation of the YAML a run depends on.

Both configuration files are otherwise checked only where they are consumed:
an unreadable ``calibration.method`` raises deep inside processing, and a
misspelled key is silently ignored, leaving a default in place with nothing to
say so. The checks here run before any data is read and report every problem at
once, separating what will fail (``error``) from what looks like a mistake but
still runs (``warning``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ZenodoError
from .zenodo import parse_creators

CALIBRATION_METHODS = frozenset({"instrument", "linear"})
EXPORT_FORMATS = frozenset({"netcdf", "nc", "zarr", "zarr2", "csv"})
MANIFEST_SECTIONS = frozenset(
    {
        "expedition",
        "inputs",
        "columns",
        "phases",
        "calibration",
        "equilibrator",
        "qc",
        "atmosphere",
        "products",
        "flux",
        "outputs",
    }
)
PROJECT_BLOCKS = frozenset({"platform", "zenodo"})
# Keys the Zenodo resolver understands; anything else is a likely typo that
# would be carried into a record silently.
ZENODO_KEYS = frozenset(
    {
        "creators",
        "community",
        "resource_type",
        "license",
        "publisher",
        "description",
        "language",
        "keywords",
        "title",
        "title_template",
        "campaign",
        "campaign_date",
        "slug",
        "slug_scheme",
        "vessel",
        "publication_date",
        "embargo",
        "notes",
        "sandbox",
        "doi",
        "submitted",
    }
)
TITLE_TOKENS = frozenset({"vessel", "campaign", "campaign_date", "year", "slug"})


@dataclass(frozen=True)
class Finding:
    """One validation result, located by its dotted path in the document."""

    severity: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity}: {self.where}: {self.message}"


class _Checker:
    """Collect findings about one document."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def error(self, where: str, message: str) -> None:
        self.findings.append(Finding("error", where, message))

    def warn(self, where: str, message: str) -> None:
        self.findings.append(Finding("warning", where, message))

    def mapping(self, value: Any, where: str) -> dict[str, Any]:
        """Return ``value`` as a mapping, reporting anything else."""
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            self.error(where, f"must be a mapping, not {type(value).__name__}")
            return {}
        return dict(value)

    def unknown_keys(self, value: Mapping[str, Any], known: frozenset[str], where: str) -> None:
        for key in sorted(set(value) - known):
            self.warn(f"{where}.{key}", "is not read by anything; check the spelling")

    def string(self, value: Any, where: str) -> None:
        if value is not None and not isinstance(value, str):
            self.error(where, f"must be a string, not {type(value).__name__}")

    def number(self, value: Any, where: str) -> None:
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            self.error(where, f"must be a number, not {type(value).__name__}")

    def boolean(self, value: Any, where: str) -> None:
        if value is not None and not isinstance(value, bool):
            self.error(where, f"must be true or false, not {type(value).__name__}")

    def int_list(self, value: Any, where: str) -> None:
        if value is None:
            return
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            self.error(where, "must be a list of integers")
            return
        for position, item in enumerate(value):
            if isinstance(item, bool) or not isinstance(item, int):
                self.error(f"{where}[{position}]", f"must be an integer, not {item!r}")


def _check_inputs(check: _Checker, manifest: Mapping[str, Any], path: Path) -> None:
    inputs = check.mapping(manifest.get("inputs"), "inputs")
    if not manifest.get("inputs"):
        check.error("inputs", "is required and must contain logs")
        return
    logs = inputs.get("logs")
    if not logs:
        check.error("inputs.logs", "is required")
    elif not isinstance(logs, str):
        check.error("inputs.logs", "must be a glob or path string")
    else:
        # Globs resolve against the manifest's own directory, as the pipeline
        # resolves them, so a manifest can be checked from anywhere.
        pattern = Path(logs)
        matches = (
            list(Path(pattern.anchor).glob(str(pattern.relative_to(pattern.anchor))))
            if pattern.is_absolute()
            else list(path.parent.glob(logs))
        )
        if not matches:
            check.warn("inputs.logs", f"matches no files: {logs}")
    check.string(inputs.get("timezone"), "inputs.timezone")


def _check_calibration(check: _Checker, manifest: Mapping[str, Any]) -> None:
    calibration = check.mapping(manifest.get("calibration"), "calibration")
    method = calibration.get("method", "instrument")
    if method not in CALIBRATION_METHODS:
        check.error(
            "calibration.method",
            f"{method!r} is not one of {', '.join(sorted(CALIBRATION_METHODS))}",
        )
    for key in ("zero_measured", "span_measured", "span_certified"):
        check.number(calibration.get(key), f"calibration.{key}")
    check.int_list(calibration.get("span_phases"), "calibration.span_phases")


def _check_qc(check: _Checker, manifest: Mapping[str, Any]) -> None:
    qc = check.mapping(manifest.get("qc"), "qc")
    check.int_list(qc.get("analysis_phases"), "qc.analysis_phases")
    for key in ("minimum_water_flow", "minimum_gas_flow"):
        check.number(qc.get(key), f"qc.{key}")
    ranges = check.mapping(qc.get("ranges"), "qc.ranges")
    for name, bounds in ranges.items():
        where = f"qc.ranges.{name}"
        if (
            not isinstance(bounds, Sequence)
            or isinstance(bounds, (str, bytes))
            or len(bounds) != 2
            or any(
                isinstance(bound, bool) or not isinstance(bound, (int, float)) for bound in bounds
            )
        ):
            check.error(where, "must be a [minimum, maximum] pair of numbers")
        elif bounds[0] >= bounds[1]:
            check.error(where, f"minimum {bounds[0]} is not below maximum {bounds[1]}")


def _check_outputs(check: _Checker, manifest: Mapping[str, Any]) -> None:
    outputs = check.mapping(manifest.get("outputs"), "outputs")
    for key in ("directory", "cache"):
        check.string(outputs.get(key), f"outputs.{key}")
    for key in ("site", "single_html", "video"):
        check.boolean(outputs.get(key), f"outputs.{key}")
    formats = outputs.get("formats")
    if formats is not None:
        if isinstance(formats, str) or not isinstance(formats, Sequence):
            check.error("outputs.formats", "must be a list, such as [netcdf, csv]")
        else:
            for item in formats:
                if str(item).lower().replace(".nc", "netcdf") not in EXPORT_FORMATS:
                    check.error(
                        "outputs.formats",
                        f"{item!r} is not one of {', '.join(sorted(EXPORT_FORMATS))}",
                    )
    options = check.mapping(outputs.get("video_options"), "outputs.video_options")
    check.string(options.get("variable"), "outputs.video_options.variable")
    check.number(options.get("fps"), "outputs.video_options.fps")


def validate_manifest_document(raw: Any, path: str | Path) -> list[Finding]:
    """Check one expedition manifest, returning every problem found."""
    path = Path(path)
    check = _Checker()
    if not isinstance(raw, Mapping):
        return [Finding("error", "manifest", "root must be a mapping")]
    check.unknown_keys(raw, MANIFEST_SECTIONS, "manifest")

    expedition = check.mapping(raw.get("expedition"), "expedition")
    if not raw.get("expedition"):
        check.error("expedition", "is required and must contain a name")
    elif not expedition.get("name"):
        check.error("expedition.name", "is required")
    _check_inputs(check, raw, path)

    columns = check.mapping(raw.get("columns"), "columns")
    for key, value in columns.items():
        check.string(value, f"columns.{key}")

    phases = check.mapping(raw.get("phases"), "phases")
    for key in ("analysis", "air"):
        check.int_list(phases.get(key), f"phases.{key}")

    _check_calibration(check, raw)

    equilibrator = check.mapping(raw.get("equilibrator"), "equilibrator")
    for key, value in equilibrator.items():
        if key in {"h2o_scale", "temperature_coefficient"}:
            check.number(value, f"equilibrator.{key}")
        else:
            check.string(value, f"equilibrator.{key}")

    _check_qc(check, raw)

    atmosphere = check.mapping(raw.get("atmosphere"), "atmosphere")
    check.int_list(atmosphere.get("air_phases"), "atmosphere.air_phases")
    check.string(atmosphere.get("time_tolerance"), "atmosphere.time_tolerance")

    products = raw.get("products", [])
    if not isinstance(products, list):
        check.error("products", "must be a list")
    else:
        for position, product in enumerate(products):
            if not isinstance(product, Mapping):
                check.error(f"products[{position}]", "must be a mapping")
            elif not product.get("name"):
                check.error(f"products[{position}].name", "is required")

    flux = check.mapping(raw.get("flux"), "flux")
    check.number(flux.get("coefficient"), "flux.coefficient")
    _check_outputs(check, raw)
    return check.findings


def validate_project_document(raw: Any, *, source: str = "project.yaml") -> list[Finding]:
    """Check one merged project configuration, returning every problem found."""
    check = _Checker()
    if not isinstance(raw, Mapping):
        return [Finding("error", source, "root must be a mapping")]
    check.unknown_keys(raw, PROJECT_BLOCKS, source)

    platform = check.mapping(raw.get("platform"), "platform")
    for key, value in platform.items():
        if isinstance(value, (Mapping, list)):
            check.error(f"platform.{key}", "must be a single value, not a list or mapping")
    if raw.get("platform") is not None and not (
        platform.get("vessel_name") or platform.get("vessel")
    ):
        check.warn("platform.vessel_name", "is unset, so reports and titles have no vessel")

    zenodo = check.mapping(raw.get("zenodo"), "zenodo")
    check.unknown_keys(zenodo, ZENODO_KEYS, "zenodo")
    for key in ("community", "resource_type", "license", "publisher", "description", "language"):
        check.string(zenodo.get(key), f"zenodo.{key}")
    check.boolean(zenodo.get("sandbox"), "zenodo.sandbox")
    for key in ("campaign", "campaign_date", "title"):
        if zenodo.get(key):
            check.warn(
                f"zenodo.{key}",
                "belongs to a single data folder; here it would name every record alike",
            )

    creators = zenodo.get("creators")
    if creators is not None:
        try:
            parse_creators(creators)
        except ZenodoError as exc:
            check.error("zenodo.creators", str(exc))

    keywords = zenodo.get("keywords")
    if keywords is not None and (
        not isinstance(keywords, list) or not all(isinstance(item, str) for item in keywords)
    ):
        check.error("zenodo.keywords", "must be a list of strings")

    template = zenodo.get("title_template")
    if template is not None:
        check.string(template, "zenodo.title_template")
        if isinstance(template, str):
            unknown = sorted(set(re.findall(r"{(\w+)}", template)) - TITLE_TOKENS)
            if unknown:
                check.error(
                    "zenodo.title_template",
                    f"uses unknown field(s) {', '.join(unknown)}; "
                    f"available: {', '.join(sorted(TITLE_TOKENS))}",
                )

    embargo = check.mapping(zenodo.get("embargo"), "zenodo.embargo")
    check.boolean(embargo.get("enabled"), "zenodo.embargo.enabled")
    if embargo.get("months") is not None and not isinstance(embargo.get("months"), int):
        check.error("zenodo.embargo.months", "must be an integer")
    return check.findings


def errors(findings: Sequence[Finding]) -> list[Finding]:
    """Return only the findings that will stop a run."""
    return [finding for finding in findings if finding.severity == "error"]
