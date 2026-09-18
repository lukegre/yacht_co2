"""Campaign manifest loading, generation, and validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from .errors import ManifestError
from .project import read_yaml
from .userconfig import shared_manifest_defaults, user_manifest_defaults
from .validation import Finding, errors, validate_manifest_document
from .zenodo import CONFIG_NAME as ZENODO_CONFIG_NAME

MANIFEST_NAME = "manifest.yaml"
DEFAULTS_NAME = "manifest.yaml"
TEMPLATES_DIRECTORY = "templates"


def default_template() -> Path:
    """Return the template a new manifest starts from.

    The user's own ``manifest.yaml`` is preferred over shared installation and
    packaged templates so that
    a fleet's settled processing choices -- its phase codes, its QC ranges --
    are the starting point for every campaign, not something re-entered per
    folder. Without one the packaged template applies unchanged.
    """
    return user_manifest_defaults() or shared_manifest_defaults() or packaged_defaults()


def packaged_defaults() -> Path:
    """Return the manifest template that ships inside the package.

    The package is asked where its own files live, so the template is found
    from a checkout, an editable install and an installed wheel alike; walking
    up from ``__file__`` only ever found a source tree. Wheels are unpacked
    into directories, so the resource is a real file on disk.
    """
    resource = resources.files(__package__).joinpath(TEMPLATES_DIRECTORY, DEFAULTS_NAME)
    with resources.as_file(resource) as path:
        return path


@dataclass(frozen=True)
class CampaignManifest:
    """Validated, immutable view of a campaign manifest."""

    path: Path
    campaign: dict[str, Any]
    inputs: dict[str, Any]
    columns: dict[str, str] = field(default_factory=dict)
    phases: dict[str, Any] = field(default_factory=dict)
    calibration: dict[str, Any] = field(default_factory=dict)
    equilibrator: dict[str, Any] = field(default_factory=dict)
    qc: dict[str, Any] = field(default_factory=dict)
    atmosphere: dict[str, Any] = field(default_factory=dict)
    products: list[dict[str, Any]] = field(default_factory=list)
    flux: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def name(self) -> str:
        return str(self.campaign["name"])

    @property
    def date(self) -> str:
        """Campaign date, as ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``."""
        return str(self.campaign.get("date") or "").strip()

    @property
    def title(self) -> str:
        """Name the campaign the way a reader should see it: name and date."""
        return f"{self.name} ({self.date})" if self.date else self.name

    @property
    def expedition(self) -> dict[str, Any]:
        """Compatibility alias for callers using the former terminology."""
        return self.campaign

    @property
    def digest(self) -> str:
        canonical = json.dumps(self.raw, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def resolve_path(self, value: str | Path) -> Path:
        """Resolve a manifest path relative to the manifest's directory."""
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.path.parent / path
        return path.resolve()


def check_manifest(path: str | Path) -> tuple[dict[str, Any], list[Finding]]:
    """Read a manifest and return it with every validation finding.

    Unlike :func:`load_manifest` this reports warnings too, and does not raise
    for a document that is merely suspect, so a caller can show the whole
    picture at once.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise ManifestError(f"manifest does not exist: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML in {path}: {exc}") from exc
    return (raw if isinstance(raw, dict) else {}), validate_manifest_document(raw, path)


ExpeditionManifest = CampaignManifest


def load_manifest(path: str | Path) -> CampaignManifest:
    """Load a campaign manifest, refusing one that cannot produce a run."""
    path = Path(path).resolve()
    raw, findings = check_manifest(path)
    fatal = errors(findings)
    if fatal:
        detail = "; ".join(f"{finding.where}: {finding.message}" for finding in fatal)
        raise ManifestError(f"invalid manifest {path}: {detail}")
    return CampaignManifest(
        path=path,
        campaign=_dated(raw.get("campaign", raw.get("expedition", {})), path),
        inputs=raw["inputs"],
        columns=raw.get("columns", {}),
        phases=raw.get("phases", {}),
        calibration=raw.get("calibration", {}),
        equilibrator=raw.get("equilibrator", {}),
        qc=raw.get("qc", {}),
        atmosphere=raw.get("atmosphere", {}),
        products=raw.get("products", []),
        flux=raw.get("flux", {}),
        outputs=raw.get("outputs", {}),
        raw=raw,
    )


def _dated(campaign: dict[str, Any], path: Path) -> dict[str, Any]:
    """Return the campaign identity, dating it from ``zenodo.yaml`` if it is not.

    ``campaign.date`` is written by :func:`build_manifest`, but a manifest built
    before it existed carries none while its folder still knows: the date is the
    one the archived record was named with.
    """
    if not isinstance(campaign, dict) or campaign.get("date"):
        return campaign
    zenodo_path = path.parent / ZENODO_CONFIG_NAME
    if not zenodo_path.is_file():
        return campaign
    date = str(read_yaml(zenodo_path).get("campaign_date") or "").strip()
    if not date:
        return campaign
    logger.info("Dating the campaign {} from {}", date, zenodo_path)
    return {**campaign, "date": date}


def build_manifest(
    zenodo: str | Path,
    output: str | Path | None = None,
    *,
    defaults: str | Path | None = None,
) -> Path:
    """Build a processing manifest from a folder's ``zenodo.yaml``.

    The generated manifest inherits processing values from the user's own
    manifest template, or from the packaged ``templates/manifest.yaml`` when
    they have none. The campaign ID follows Zenodo's slug rule: an
    explicit slug wins, otherwise the data-folder name is used. A Zenodo
    campaign is preferred as the concise name; an explicit title is accepted
    as a fallback.
    """
    zenodo_path = Path(zenodo).resolve()
    if not zenodo_path.is_file():
        raise ManifestError(f"Zenodo configuration does not exist: {zenodo_path}")
    defaults_path = Path(defaults).resolve() if defaults is not None else default_template()
    if not defaults_path.is_file():
        raise ManifestError(f"manifest defaults do not exist: {defaults_path}")

    logger.info("Building campaign manifest from {}", zenodo_path)
    zenodo_document = read_yaml(zenodo_path)
    logger.info("Loading manifest defaults from {}", defaults_path)
    template = read_yaml(defaults_path)
    name = str(zenodo_document.get("campaign") or zenodo_document.get("title") or "").strip()
    if not name:
        raise ManifestError(f"{zenodo_path} needs campaign or title to supply campaign.name")

    date = str(zenodo_document.get("campaign_date") or "").strip()
    campaign_id = str(zenodo_document.get("slug") or zenodo_path.parent.name).strip()
    if not campaign_id or any(character.isspace() for character in campaign_id):
        raise ManifestError(f"invalid campaign id derived from Zenodo slug: {campaign_id!r}")
    logger.info("Resolved campaign id {!r} and name {!r}", campaign_id, name)

    repository = str(zenodo_document.get("doi") or "").strip()
    if not repository:
        raise ManifestError(f"{zenodo_path} needs doi to supply the default inputs.repository")

    document = dict(template)
    document["campaign"] = {"id": campaign_id, "name": name}
    if date:
        document["campaign"]["date"] = date
    document["inputs"] = {**document.get("inputs", {}), "repository": repository}
    document.pop("expedition", None)
    destination = (
        Path(output).resolve() if output is not None else zenodo_path.with_name(MANIFEST_NAME)
    )
    if destination.exists():
        raise ManifestError(f"manifest already exists: {destination}")

    findings = validate_manifest_document(document, destination)
    fatal = errors(findings)
    if fatal:
        detail = "; ".join(f"{finding.where}: {finding.message}" for finding in fatal)
        raise ManifestError(f"invalid manifest defaults {defaults_path}: {detail}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    logger.success("Built campaign manifest {}", destination)
    return destination
