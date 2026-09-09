"""Expedition manifest loading and validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ManifestError
from .validation import Finding, errors, validate_manifest_document


@dataclass(frozen=True)
class ExpeditionManifest:
    """Validated, immutable view of ``expedition.yaml``."""

    path: Path
    expedition: dict[str, Any]
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
        return str(self.expedition["name"])

    @property
    def digest(self) -> str:
        canonical = json.dumps(self.raw, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


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


def load_manifest(path: str | Path) -> ExpeditionManifest:
    """Load an expedition manifest, refusing one that cannot produce a run."""
    path = Path(path).resolve()
    raw, findings = check_manifest(path)
    fatal = errors(findings)
    if fatal:
        detail = "; ".join(f"{finding.where}: {finding.message}" for finding in fatal)
        raise ManifestError(f"invalid manifest {path}: {detail}")
    return ExpeditionManifest(
        path=path,
        expedition=raw["expedition"],
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
