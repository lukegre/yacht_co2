"""Expedition manifest loading and validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ManifestError


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


def load_manifest(path: str | Path) -> ExpeditionManifest:
    """Load an expedition manifest and enforce required top-level contracts."""
    path = Path(path).resolve()
    if not path.is_file():
        raise ManifestError(f"manifest does not exist: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a mapping")
    for key in ("expedition", "inputs"):
        if not isinstance(raw.get(key), dict):
            raise ManifestError(f"manifest requires a {key!r} mapping")
    if not raw["expedition"].get("name"):
        raise ManifestError("expedition.name is required")
    if not raw["inputs"].get("logs"):
        raise ManifestError("inputs.logs is required")
    products = raw.get("products", [])
    if not isinstance(products, list):
        raise ManifestError("products must be a list")
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
        products=products,
        flux=raw.get("flux", {}),
        outputs=raw.get("outputs", {}),
        raw=raw,
    )
